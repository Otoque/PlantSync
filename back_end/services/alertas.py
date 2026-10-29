"""Monta os alertas que o painel mostra para o lote em transito."""

from models.tabelas import Fruta
from services.analise import ACOES_CURTAS, GRAVIDADE
from services.datas import formatar_utc, hora_recife
from services.lotes import buscar_e_analisar, lote_em_transito


def alerta_calor(lote, analise):
    """Alerta do lado quente: graus-hora acima do teto da faixa."""
    nivel = analise["nivel_acima"]
    # :.0f mostra os graus-hora sem casas decimais; :g tira o ".0" do limite (2.0 vira 2).
    mensagem = (
        f"Lote {lote.id} ({lote.fruta_id}) acumulou {analise['graus_hora_acima']:.0f} °C·h "
        f"acima de {lote.temp_max_c:g} °C: {ACOES_CURTAS[nivel]}."
    )
    return alerta_risco_termico(lote, analise, "acima", nivel, mensagem)


def alerta_frio(lote, analise, risco_no_frio):
    """
    Alerta do lado frio: graus-hora abaixo do piso da faixa. Se a fruta
    tiver um dano conhecido no frio (ex.: corte negro), ele entra no texto.
    """
    nivel = analise["nivel_abaixo"]
    acao = ACOES_CURTAS[nivel]
    if risco_no_frio:
        acao = f"risco de {risco_no_frio}, {acao}"
    mensagem = (
        f"Lote {lote.id} ({lote.fruta_id}) acumulou {analise['graus_hora_abaixo']:.0f} °C·h "
        f"abaixo de {lote.temp_min_c:g} °C: {acao}."
    )
    return alerta_risco_termico(lote, analise, "abaixo", nivel, mensagem)


def alerta_risco_termico(lote, analise, lado, nivel, mensagem):
    return {
        "lote_id": lote.id,
        "fruta": lote.fruta_id,
        "tipo": "risco_termico",
        "lado": lado,
        "nivel": nivel,
        "mensagem": mensagem,
        "data_hora": analise["ultima_leitura"],
    }


def alerta_porta_aberta(lote, evento):
    mensagem = (
        f"Lote {lote.id} ({lote.fruta_id}): porta aberta por "
        f"{evento['duracao_min']:.0f} min às {hora_recife(evento['inicio'])}."
    )
    return {
        "lote_id": lote.id,
        "fruta": lote.fruta_id,
        "tipo": "porta_aberta",
        "lado": None,
        "nivel": "AMARELO",
        "mensagem": mensagem,
        "data_hora": evento["inicio"],
    }


def gerar_alertas(sessao):
    """
    Alertas do lote em transito: um de calor e um de frio (cada um so se o
    seu lado nao for VERDE) e um para cada abertura de porta.
    Lote encerrado ou sem leituras nao gera alerta de risco.
    """
    lote = lote_em_transito(sessao)
    if lote is None:
        return []

    alertas = []
    analise = buscar_e_analisar(sessao, lote)
    # SEM_DADOS nao esta em GRAVIDADE; o .get devolve 0 e nao gera alerta.
    if GRAVIDADE.get(analise["nivel_acima"], 0) > 0:
        alertas.append(alerta_calor(lote, analise))
    if GRAVIDADE.get(analise["nivel_abaixo"], 0) > 0:
        fruta = sessao.get(Fruta, lote.fruta_id)
        alertas.append(alerta_frio(lote, analise, fruta.risco_no_frio))
    for evento in analise["eventos_porta"]:
        alertas.append(alerta_porta_aberta(lote, evento))

    # Mais grave primeiro; no mesmo nivel, o mais recente primeiro.
    alertas.sort(key=lambda alerta: (GRAVIDADE[alerta["nivel"]], alerta["data_hora"]), reverse=True)

    # A data so vira texto depois de ordenar, para ordenar por data e nao por texto.
    for alerta in alertas:
        alerta["data_hora"] = formatar_utc(alerta["data_hora"])
    return alertas
