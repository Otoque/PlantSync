#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 PLANTSYNC - Analise Exploratoria da Telemetria de Container
 Projeto Integrador ADS 4o Periodo - Camada de Data Science
-------------------------------------------------------------------------------
 O que este script faz:
   1. Carrega a telemetria exportada do canal ThingSpeak (CSV).
      Se nenhum CSV for encontrado, gera uma viagem sintetica de 72 h para
      que o pipeline possa ser demonstrado antes da coleta real.
   2. Normaliza e audita a qualidade dos dados (nulos, duplicatas, outliers,
      lacunas de amostragem).
   3. Calcula a metrica central do projeto: GRAUS-HORA DE ABUSO TERMICO,
      que quantifica a severidade acumulada da quebra da cadeia do frio.
   4. Detecta anomalias termicas por desvio movel (z-score em janela).
   5. Identifica eventos de abertura de porta pela luminosidade.
   6. Gera graficos e um relatorio textual em analytics/outputs/.

 Uso:
   python eda_plantsync.py                      # modo demo (dados sinteticos)
   python eda_plantsync.py --csv feeds.csv      # dados reais do ThingSpeak
   python eda_plantsync.py --demo --horas 120   # demo com viagem mais longa
===============================================================================
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # backend sem interface grafica
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------------------------
# PARAMETROS DE NEGOCIO - espelham as constantes do firmware
# ---------------------------------------------------------------------------
TEMP_MIN_SEGURA  = 0.0
TEMP_MAX_SEGURA  = 4.0
UR_MIN_SEGURA    = 85.0
UR_MAX_SEGURA    = 95.0
AGUA_LIVRE_MAX   = 60.0
LUX_PORTA_ABERTA = 300.0

PASTA_SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# Paleta consistente em todo o relatorio
COR_TEMP   = "#C8102E"
COR_UR     = "#0B6E4F"
COR_AGUA   = "#1D4E89"
COR_LUZ    = "#E2A03F"
COR_NEUTRA = "#6B7280"


# ===========================================================================
# 1. AQUISICAO
# ===========================================================================
def gerar_dados_sinteticos(horas=72, passo_min=5, semente=42):
    """
    Simula uma viagem Petrolina -> Porto de Suape com uma falha real de
    refrigeracao: o compressor degrada na 30a hora e so e normalizado 6 h
    depois, apos uma parada com abertura de porta.
    """
    rng = np.random.default_rng(semente)
    n = int(horas * 60 / passo_min)
    inicio = datetime.now() - timedelta(hours=horas)
    ts = [inicio + timedelta(minutes=passo_min * i) for i in range(n)]
    h = np.arange(n) * passo_min / 60.0          # horas decorridas

    # --- Temperatura: setpoint 2 C com ondulacao do ciclo do compressor ----
    temp = 2.0 + 0.45 * np.sin(2 * np.pi * h / 1.5) + rng.normal(0, 0.18, n)

    # Falha progressiva do compressor entre 30 h e 36 h
    falha = (h >= 30) & (h <= 36)
    rampa = np.clip((h[falha] - 30) / 3.0, 0, 2.0)
    temp[falha] += rampa * 3.2

    # Recuperacao gradual apos a intervencao
    recup = (h > 36) & (h <= 40)
    temp[recup] += np.linspace(4.5, 0, recup.sum())

    # --- Umidade relativa: anticorrelacionada com a temperatura -----------
    ur = 91.0 - (temp - 2.0) * 2.4 + rng.normal(0, 0.9, n)
    ur = np.clip(ur, 40, 100)

    # --- Agua livre no piso: sobe com condensacao pos-falha ---------------
    agua = 38.0 + rng.normal(0, 2.5, n)
    agua[h > 33] += np.clip((h[h > 33] - 33) * 1.6, 0, 32)
    agua = np.clip(agua, 0, 100)

    # --- Luminosidade: escuro, exceto em 3 aberturas de porta -------------
    luz = np.abs(rng.normal(4, 2, n))
    for hora_abertura, duracao_min in [(12.0, 15), (36.0, 40), (58.0, 10)]:
        janela = (h >= hora_abertura) & (h <= hora_abertura + duracao_min / 60.0)
        luz[janela] = rng.uniform(420, 880, janela.sum())

    # RSSI degrada quando o caminhao passa por trechos sem cobertura.
    rssi = -62 + rng.normal(0, 5, n)
    rssi[(h > 44) & (h < 49)] -= 22          # trecho de sombra de sinal

    df = pd.DataFrame({
        "created_at": ts,
        "entry_id": np.arange(1, n + 1),
        "field1": np.round(temp, 2),
        "field2": np.round(ur, 2),
        "field3": np.round(rssi, 0),
        "field4": np.round(agua, 2),
        "field5": np.round(luz, 0),
    })

    # --- Sujeira realista: o mundo real nao entrega dados limpos ----------
    idx_nulos = rng.choice(n, size=max(1, int(n * 0.012)), replace=False)
    df.loc[idx_nulos, "field1"] = np.nan

    idx_outlier = rng.choice(n, size=4, replace=False)
    df.loc[idx_outlier, "field1"] = rng.choice([-127.0, 85.0, 999.0, -40.5], 4)

    # Duplicatas de retransmissao (o ESP32 reenviou apos timeout)
    df = pd.concat([df, df.iloc[[10, 11, 250]]], ignore_index=True)
    df = df.sort_values("created_at").reset_index(drop=True)

    return df


def carregar_csv(caminho):
    if not os.path.exists(caminho):
        sys.exit(f"[ERRO] Arquivo nao encontrado: {caminho}")
    df = pd.read_csv(caminho)
    print(f"[INFO ] CSV carregado: {caminho} ({len(df)} linhas brutas)")
    return df


# ===========================================================================
# 2. LIMPEZA E AUDITORIA DE QUALIDADE
# ===========================================================================
def normalizar(df):
    """Renomeia os campos do ThingSpeak para nomes de dominio."""
    # Mapeamento do canal ThingSpeak da equipe.
    # field1/field2 vem do prototipo de 16/09; field3 (RSSI) foi mantido do
    # original; field4 em diante sao os sensores acrescentados na v2.
    mapa = {
        "field1": "temperatura_c",
        "field2": "umidade_ar_pct",
        "field3": "rssi_dbm",
        "field4": "agua_livre_pct",
        "field5": "luminosidade_lux",
        "field6": "alertas_bitmask",
        "field7": "risco_0_100",
    }
    df = df.rename(columns={k: v for k, v in mapa.items() if k in df.columns})
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["created_at"] = df["created_at"].dt.tz_convert("America/Recife").dt.tz_localize(None)

    for col in mapa.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("created_at").reset_index(drop=True)


def auditar_e_limpar(df):
    """Aplica as mesmas regras Fail-Fast do firmware, agora em lote."""
    relatorio = {"linhas_brutas": len(df)}

    # a) Duplicatas de retransmissao
    antes = len(df)
    df = df.drop_duplicates(subset=["created_at"], keep="first")
    relatorio["duplicatas_removidas"] = antes - len(df)

    # b) Registros sem timestamp valido
    antes = len(df)
    df = df.dropna(subset=["created_at"])
    relatorio["timestamps_invalidos"] = antes - len(df)

    # c) Nulos na variavel critica
    relatorio["nulos_temperatura"] = int(df["temperatura_c"].isna().sum())

    # d) Outliers fisicamente impossiveis (mesmo criterio do firmware)
    fora_faixa = (df["temperatura_c"] < -40) | (df["temperatura_c"] > 80)
    relatorio["outliers_fisicos"] = int(fora_faixa.sum())
    df.loc[fora_faixa, "temperatura_c"] = np.nan

    # e) Outliers estatisticos por IQR, avaliados apos o corte fisico.
    #
    #    DECISAO ANALITICA: estes pontos sao apenas MARCADOS, nunca removidos.
    #    Numa serie de cadeia do frio o outlier estatistico costuma ser
    #    exatamente o evento de interesse - a falha de refrigeracao. Remove-lo
    #    equivaleria a apagar a evidencia do prejuizo que o projeto existe
    #    para detectar. So o outlier FISICO (item d) e descartado, porque
    #    esse sim indica sensor com defeito.
    q1, q3 = df["temperatura_c"].quantile([0.25, 0.75])
    iqr = q3 - q1
    lim_inf, lim_sup = q1 - 3 * iqr, q3 + 3 * iqr
    df["outlier_estatistico"] = (df["temperatura_c"] < lim_inf) | \
                                (df["temperatura_c"] > lim_sup)
    relatorio["outliers_estatisticos"] = int(df["outlier_estatistico"].sum())
    relatorio["faixa_iqr"] = (round(lim_inf, 2), round(lim_sup, 2))

    # f) Imputacao por interpolacao temporal - lacunas curtas de sensor
    #    nao justificam descartar a janela inteira da viagem.
    df["temperatura_c"] = df["temperatura_c"].interpolate(method="linear", limit=6)
    df["umidade_ar_pct"] = df["umidade_ar_pct"].interpolate(method="linear", limit=6)

    antes = len(df)
    df = df.dropna(subset=["temperatura_c"])
    relatorio["descartados_sem_recuperacao"] = antes - len(df)

    # g) Lacunas de amostragem (o dispositivo ficou mudo?)
    deltas = df["created_at"].diff().dt.total_seconds() / 60.0
    passo_tipico = deltas.median()
    lacunas = deltas[deltas > passo_tipico * 3]
    relatorio["passo_mediano_min"] = round(float(passo_tipico), 2)
    relatorio["lacunas_detectadas"] = int(len(lacunas))
    relatorio["maior_lacuna_min"] = round(float(lacunas.max()), 1) if len(lacunas) else 0.0

    relatorio["linhas_finais"] = len(df)
    relatorio["taxa_aproveitamento"] = round(len(df) / relatorio["linhas_brutas"] * 100, 2)

    return df.reset_index(drop=True), relatorio


# ===========================================================================
# 3. ENGENHARIA DE ATRIBUTOS E ANALISE
# ===========================================================================
def enriquecer(df):
    """Deriva as variaveis que sustentam a decisao logistica."""
    df = df.copy()

    # Intervalo real entre amostras, em horas - base do calculo de graus-hora
    dt_h = df["created_at"].diff().dt.total_seconds().div(3600).fillna(0)
    df["intervalo_h"] = dt_h

    # Desvio acima do teto seguro
    df["excesso_c"] = (df["temperatura_c"] - TEMP_MAX_SEGURA).clip(lower=0)

    # GRAUS-HORA DE ABUSO TERMICO: integral do excesso no tempo.
    # E a metrica que a industria usa para estimar perda de vida util.
    df["graus_hora"] = df["excesso_c"] * df["intervalo_h"]
    df["graus_hora_acum"] = df["graus_hora"].cumsum()

    # Anomalia por desvio movel: pega mudancas de regime que um limiar fixo
    # nao enxerga (ex.: oscilacao anormal ainda dentro da faixa segura).
    #
    # A janela e TRAILING (olha so para o passado imediato, via shift), nao
    # centrada. Uma janela centrada incorpora a propria falha no baseline e
    # acaba normalizando o evento que deveria denunciar - a rampa lenta do
    # compressor passaria despercebida.
    janela = max(8, int(len(df) * 0.015))
    base = df["temperatura_c"].shift(1)
    media_movel = base.rolling(janela, min_periods=6).mean()
    desvio_movel = base.rolling(janela, min_periods=6).std()

    # Piso no desvio: em regime muito estavel o desvio tende a zero e
    # qualquer ondulacao normal viraria "anomalia".
    desvio_movel = desvio_movel.clip(lower=0.15)

    df["z_score"] = (df["temperatura_c"] - media_movel) / desvio_movel

    # Criterio duplo: significancia estatistica E relevancia pratica.
    # So o z-score marcaria como anomalia a ondulacao normal do compressor,
    # que e estatisticamente incomum mas operacionalmente irrelevante.
    # Exigir tambem um desvio absoluto minimo elimina esse falso positivo.
    desvio_absoluto = (df["temperatura_c"] - media_movel).abs()
    df["anomalia"] = (df["z_score"].abs() > 3) & (desvio_absoluto > 0.8)

    # Flags de negocio
    df["fora_faixa_termica"] = (df["temperatura_c"] > TEMP_MAX_SEGURA) | \
                               (df["temperatura_c"] < TEMP_MIN_SEGURA)
    if "umidade_ar_pct" in df:
        df["ur_fora_faixa"] = (df["umidade_ar_pct"] < UR_MIN_SEGURA) | \
                              (df["umidade_ar_pct"] > UR_MAX_SEGURA)
    if "luminosidade_lux" in df:
        df["porta_aberta"] = df["luminosidade_lux"] > LUX_PORTA_ABERTA
    if "agua_livre_pct" in df:
        df["agua_critica"] = df["agua_livre_pct"] > AGUA_LIVRE_MAX

    return df


def detectar_eventos_porta(df):
    """Agrupa amostras consecutivas de luz alta em eventos discretos."""
    if "porta_aberta" not in df:
        return pd.DataFrame()

    grupo = (df["porta_aberta"] != df["porta_aberta"].shift()).cumsum()
    eventos = []
    for _, bloco in df[df["porta_aberta"]].groupby(grupo[df["porta_aberta"]]):
        eventos.append({
            "inicio": bloco["created_at"].iloc[0],
            "fim": bloco["created_at"].iloc[-1],
            "duracao_min": round(
                (bloco["created_at"].iloc[-1] - bloco["created_at"].iloc[0]).total_seconds() / 60, 1
            ),
            "lux_max": round(float(bloco["luminosidade_lux"].max()), 0),
            "temp_media_c": round(float(bloco["temperatura_c"].mean()), 2),
        })
    return pd.DataFrame(eventos)


def classificar_carga(graus_hora_total):
    """
    Traduz graus-hora acumulados em uma recomendacao operacional.
    Limiares calibrados para uva de mesa; devem ser revalidados com o
    produtor parceiro antes da entrega final.
    """
    if graus_hora_total == 0:
        return "VERDE", "Cadeia do frio integra. Carga liberada sem ressalvas."
    if graus_hora_total < 5:
        return "VERDE", "Desvio marginal. Vida util preservada."
    if graus_hora_total < 20:
        return "AMARELO", "Abuso termico moderado. Priorizar esta carga na expedicao."
    if graus_hora_total < 50:
        return "LARANJA", "Abuso relevante. Inspecao fisica obrigatoria antes do embarque."
    return "VERMELHO", "Abuso severo. Redirecionar para mercado interno ou processamento."


# ===========================================================================
# 4. VISUALIZACAO
# ===========================================================================
def gerar_graficos(df, eventos):
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    fig, eixos = plt.subplots(4, 1, figsize=(13, 13), sharex=True)
    fig.suptitle("PlantSync - Perfil da Viagem do Container CTR-PNZ-0042",
                 fontsize=15, fontweight="bold", y=0.985)

    # --- (1) Temperatura e faixa segura ---
    ax = eixos[0]
    ax.plot(df["created_at"], df["temperatura_c"], color=COR_TEMP, lw=1.4,
            label="Temperatura medida")
    ax.axhspan(TEMP_MIN_SEGURA, TEMP_MAX_SEGURA, color="#16A34A", alpha=0.12,
               label=f"Faixa segura ({TEMP_MIN_SEGURA:.0f}-{TEMP_MAX_SEGURA:.0f} C)")
    ax.axhline(TEMP_MAX_SEGURA, color="#16A34A", ls="--", lw=1)

    fora = df[df["fora_faixa_termica"]]
    ax.scatter(fora["created_at"], fora["temperatura_c"], color=COR_TEMP,
               s=9, zorder=5, label=f"Fora da faixa ({len(fora)} amostras)")

    anom = df[df["anomalia"]]
    if len(anom):
        ax.scatter(anom["created_at"], anom["temperatura_c"], facecolors="none",
                   edgecolors="black", s=70, lw=1.2, zorder=6,
                   label=f"Anomalia estatistica ({len(anom)})")

    ax.set_ylabel("Temperatura (C)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)

    # --- (2) Umidade relativa ---
    ax = eixos[1]
    ax.plot(df["created_at"], df["umidade_ar_pct"], color=COR_UR, lw=1.3,
            label="Umidade relativa do ar")
    ax.axhspan(UR_MIN_SEGURA, UR_MAX_SEGURA, color="#16A34A", alpha=0.12,
               label=f"Faixa ideal ({UR_MIN_SEGURA:.0f}-{UR_MAX_SEGURA:.0f}%)")
    if "agua_livre_pct" in df:
        ax.plot(df["created_at"], df["agua_livre_pct"], color=COR_AGUA, lw=1.2,
                ls="-.", label="Agua livre no piso")
        ax.axhline(AGUA_LIVRE_MAX, color=COR_AGUA, ls=":", lw=1)
    ax.set_ylabel("Percentual (%)")
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)

    # --- (3) Luminosidade / aberturas de porta ---
    ax = eixos[2]
    ax.fill_between(df["created_at"], 0, df["luminosidade_lux"],
                    color=COR_LUZ, alpha=0.65, label="Luminosidade interna")
    ax.axhline(LUX_PORTA_ABERTA, color="#991B1B", ls="--", lw=1.2,
               label=f"Limiar de porta aberta ({LUX_PORTA_ABERTA:.0f} lux)")
    for _, ev in eventos.iterrows():
        ax.axvspan(ev["inicio"], ev["fim"], color="#991B1B", alpha=0.16)
    ax.set_ylabel("Luminosidade (lux)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)

    # --- (4) Graus-hora acumulados ---
    ax = eixos[3]
    ax.fill_between(df["created_at"], 0, df["graus_hora_acum"],
                    color=COR_TEMP, alpha=0.30)
    ax.plot(df["created_at"], df["graus_hora_acum"], color=COR_TEMP, lw=1.8,
            label="Abuso termico acumulado")
    for limiar, rotulo, cor in [(5, "Amarelo", "#EAB308"),
                                (20, "Laranja", "#EA580C"),
                                (50, "Vermelho", "#991B1B")]:
        if df["graus_hora_acum"].max() > limiar * 0.5:
            ax.axhline(limiar, color=cor, ls="--", lw=1)
            # Rotulo a direita, fora da area ocupada pela legenda.
            ax.text(df["created_at"].iloc[-1], limiar, f"{rotulo} ", color=cor,
                    fontsize=8, va="bottom", ha="right", fontweight="bold")
    ax.set_ylabel("Graus-hora (C-h)")
    ax.set_xlabel("Data / hora (America/Recife)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))
    fig.autofmt_xdate()
    plt.tight_layout(rect=[0, 0, 1, 0.975])

    caminho = os.path.join(PASTA_SAIDA, "01_perfil_viagem.png")
    fig.savefig(caminho, dpi=140)
    plt.close(fig)
    print(f"[SAIDA] Grafico salvo: {caminho}")

    # --- Grafico 2: distribuicao e correlacao ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    ax1.hist(df["temperatura_c"], bins=40, color=COR_TEMP, alpha=0.8,
             edgecolor="white")
    ax1.axvline(TEMP_MAX_SEGURA, color="#16A34A", ls="--", lw=1.5,
                label="Teto seguro (4 C)")
    ax1.set_title("Distribuicao da temperatura", fontweight="bold")
    ax1.set_xlabel("Temperatura (C)")
    ax1.set_ylabel("Frequencia")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.25)

    ax2.scatter(df["temperatura_c"], df["umidade_ar_pct"], s=8,
                c=df["graus_hora_acum"], cmap="YlOrRd", alpha=0.75)
    r = df["temperatura_c"].corr(df["umidade_ar_pct"])
    ax2.set_title(f"Temperatura x Umidade relativa (r = {r:.3f})", fontweight="bold")
    ax2.set_xlabel("Temperatura (C)")
    ax2.set_ylabel("Umidade relativa (%)")
    ax2.grid(alpha=0.25)

    plt.tight_layout()
    caminho = os.path.join(PASTA_SAIDA, "02_distribuicao_correlacao.png")
    fig.savefig(caminho, dpi=140)
    plt.close(fig)
    print(f"[SAIDA] Grafico salvo: {caminho}")


# ===========================================================================
# 5. RELATORIO
# ===========================================================================
def emitir_relatorio(df, relatorio_qualidade, eventos):
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    gh_total = float(df["graus_hora_acum"].iloc[-1])
    farol, recomendacao = classificar_carga(gh_total)
    duracao_h = (df["created_at"].iloc[-1] - df["created_at"].iloc[0]).total_seconds() / 3600

    linhas = []
    add = linhas.append

    add("=" * 78)
    add(" PLANTSYNC - RELATORIO DE ANALISE EXPLORATORIA DA VIAGEM")
    add(" Projeto Integrador ADS 4o Periodo")
    add(f" Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add("=" * 78)

    add("")
    add("1. AUDITORIA DE QUALIDADE DOS DADOS")
    add("-" * 78)
    q = relatorio_qualidade
    add(f"  Linhas brutas recebidas.............: {q['linhas_brutas']}")
    add(f"  Duplicatas de retransmissao.........: {q['duplicatas_removidas']}")
    add(f"  Timestamps invalidos................: {q['timestamps_invalidos']}")
    add(f"  Nulos na temperatura................: {q['nulos_temperatura']}")
    add(f"  Outliers fisicamente impossiveis....: {q['outliers_fisicos']}")
    add(f"  Outliers estatisticos (3x IQR)......: {q['outliers_estatisticos']} "
        f"(MARCADOS, nao removidos)")
    add(f"  Faixa aceita pelo IQR...............: {q['faixa_iqr'][0]} a {q['faixa_iqr'][1]} C")
    add("     ^ outlier estatistico aqui e a propria falha de refrigeracao:")
    add("       descarta-lo apagaria a evidencia que o projeto quer capturar.")
    add(f"  Descartados sem recuperacao.........: {q['descartados_sem_recuperacao']}")
    add(f"  Passo mediano de amostragem.........: {q['passo_mediano_min']} min")
    add(f"  Lacunas de transmissao..............: {q['lacunas_detectadas']} "
        f"(maior: {q['maior_lacuna_min']} min)")
    add(f"  Linhas validas para analise.........: {q['linhas_finais']}")
    add(f"  Taxa de aproveitamento..............: {q['taxa_aproveitamento']}%")

    add("")
    add("2. ESTATISTICA DESCRITIVA")
    add("-" * 78)
    colunas = [c for c in ["temperatura_c", "umidade_ar_pct",
                           "agua_livre_pct", "luminosidade_lux"] if c in df]
    add(df[colunas].describe().round(2).to_string())

    add("")
    add("3. CONFORMIDADE COM A CADEIA DO FRIO")
    add("-" * 78)
    n = len(df)
    fora = int(df["fora_faixa_termica"].sum())
    add(f"  Duracao monitorada..................: {duracao_h:.1f} h")
    add(f"  Amostras analisadas.................: {n}")
    add(f"  Amostras fora da faixa termica......: {fora} ({fora / n * 100:.1f}%)")
    add(f"  Temperatura maxima registrada.......: {df['temperatura_c'].max():.2f} C")
    add(f"  Temperatura minima registrada.......: {df['temperatura_c'].min():.2f} C")
    add(f"  Temperatura media...................: {df['temperatura_c'].mean():.2f} C")
    add(f"  Anomalias estatisticas (|z| > 3)....: {int(df['anomalia'].sum())}")
    if "ur_fora_faixa" in df:
        add(f"  Amostras com UR fora da faixa.......: {int(df['ur_fora_faixa'].sum())}")
    if "agua_critica" in df:
        add(f"  Amostras com agua livre critica.....: {int(df['agua_critica'].sum())}")

    add("")
    add("4. EVENTOS DE ABERTURA DE PORTA")
    add("-" * 78)
    if len(eventos):
        add(f"  {len(eventos)} evento(s) detectado(s) por luminosidade:")
        for i, ev in eventos.iterrows():
            add(f"    [{i + 1}] {ev['inicio']:%d/%m %H:%M} -> {ev['fim']:%H:%M} "
                f"| {ev['duracao_min']:>5.1f} min | pico {ev['lux_max']:.0f} lux "
                f"| temp media {ev['temp_media_c']:.2f} C")
    else:
        add("  Nenhum evento de abertura detectado durante o trajeto.")

    add("")
    add("5. INDICE DE ABUSO TERMICO E DECISAO")
    add("-" * 78)
    add(f"  Graus-hora acumulados acima de {TEMP_MAX_SEGURA:.0f} C...: {gh_total:.2f} C-h")
    if fora:
        pior = df.loc[df["excesso_c"].idxmax()]
        add(f"  Pico de excesso.....................: +{pior['excesso_c']:.2f} C "
            f"em {pior['created_at']:%d/%m %H:%M}")
        janela = df[df["excesso_c"] > 0]
        add(f"  Tempo total em abuso................: {janela['intervalo_h'].sum():.2f} h")
    add("")
    add(f"  >>> CLASSIFICACAO DA CARGA: {farol}")
    add(f"  >>> {recomendacao}")

    add("")
    add("6. PROXIMOS PASSOS DA MODELAGEM")
    add("-" * 78)
    add("  - Validar os limiares de graus-hora com o produtor parceiro.")
    add("  - Rotular cargas historicas com a perda real observada no destino")
    add("    para treinar um regressor de vida util remanescente.")
    add("  - Avaliar previsao de temperatura a 2 h com series temporais, dando")
    add("    ao operador janela de reacao antes do rompimento da faixa segura.")
    add("=" * 78)

    texto = "\n".join(linhas)
    print()
    print(texto)

    caminho = os.path.join(PASTA_SAIDA, "relatorio_eda.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(f"\n[SAIDA] Relatorio salvo: {caminho}")

    caminho_csv = os.path.join(PASTA_SAIDA, "telemetria_tratada.csv")
    df.to_csv(caminho_csv, index=False, encoding="utf-8")
    print(f"[SAIDA] Dataset tratado: {caminho_csv}")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Analise exploratoria da telemetria PlantSync.")
    parser.add_argument("--csv", help="CSV exportado do canal ThingSpeak.")
    parser.add_argument("--demo", action="store_true",
                        help="Forca a geracao de dados sinteticos.")
    parser.add_argument("--horas", type=int, default=72,
                        help="Duracao da viagem simulada (default: 72).")
    args = parser.parse_args()

    print("=" * 78)
    print(" PLANTSYNC - Pipeline de Analise Exploratoria")
    print("=" * 78)

    if args.csv and not args.demo:
        bruto = carregar_csv(args.csv)
    else:
        print(f"[INFO ] Modo demonstracao: gerando viagem sintetica de {args.horas} h.")
        print("[INFO ] Substitua por --csv feeds.csv quando houver telemetria real.")
        bruto = gerar_dados_sinteticos(horas=args.horas)

    df = normalizar(bruto)
    df, qualidade = auditar_e_limpar(df)
    df = enriquecer(df)
    eventos = detectar_eventos_porta(df)

    gerar_graficos(df, eventos)
    emitir_relatorio(df, qualidade, eventos)

    print("\n[OK   ] Pipeline concluido com sucesso.")


if __name__ == "__main__":
    main()
