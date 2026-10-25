"""
Analise da viagem de um lote: graus-hora, nivel de risco e aberturas de porta.

A logica foi trazida de analytics/eda_plantsync.py (funcoes enriquecer,
classificar_carga e detectar_eventos_porta), reescrita sem pandas para a API
ficar leve. Se um limiar mudar aqui, mude tambem no pipeline analitico.

Cada leitura e um dicionario com as chaves:
    data_hora (datetime), temperatura_c, umidade_pct, luminosidade_lux
"""

# Faixa fisica do sensor: fora dela a leitura e defeito, nao fenomeno
# (mesmo criterio Fail-Fast do firmware e do pipeline analitico).
TEMP_FISICA_MIN = -40.0
TEMP_FISICA_MAX = 80.0

# Luz acima disso dentro do compartimento lacrado indica porta aberta.
LUX_PORTA_ABERTA = 300.0

# Limiares de graus-hora definidos pela equipe no pipeline analitico.
# Ainda precisam ser validados com um produtor parceiro.
LIMITE_AMARELO = 5.0
LIMITE_LARANJA = 20.0
LIMITE_VERMELHO = 50.0

RECOMENDACOES = {
    "VERDE": "Cadeia do frio íntegra ou desvio marginal. Carga liberada.",
    "AMARELO": "Abuso térmico moderado. Priorizar esta carga na expedição.",
    "LARANJA": "Abuso relevante. Inspeção física obrigatória antes do embarque.",
    "VERMELHO": "Abuso severo. Redirecionar para mercado interno ou processamento.",
    "SEM_DADOS": "Nenhuma leitura recebida para este lote.",
}

# Versao curta da recomendacao, usada no texto dos alertas.
ACOES_CURTAS = {
    "AMARELO": "priorizar na expedição",
    "LARANJA": "inspecionar antes do embarque",
    "VERMELHO": "redirecionar para mercado interno ou processamento",
}


def temperatura_valida(temperatura):
    """Diz se a temperatura pode entrar na analise."""
    if temperatura is None:
        return False
    return TEMP_FISICA_MIN <= temperatura <= TEMP_FISICA_MAX


def porta_aberta(luminosidade):
    if luminosidade is None:
        return False
    return luminosidade > LUX_PORTA_ABERTA


def fora_da_faixa(valor, minimo, maximo):
    if valor is None:
        return False
    return valor < minimo or valor > maximo


def calcular_graus_hora(leituras, temp_max):
    """
    Soma o excesso de temperatura acima de temp_max multiplicado pelo tempo.

    Igual ao pipeline analitico: o excesso de cada leitura vale para o
    intervalo desde a leitura anterior. As leituras devem vir em ordem.
    """
    total = 0.0
    anterior = None
    for leitura in leituras:
        if anterior is not None:
            intervalo_h = (leitura["data_hora"] - anterior["data_hora"]).total_seconds() / 3600
            excesso = max(0.0, leitura["temperatura_c"] - temp_max)
            total += excesso * intervalo_h
        anterior = leitura
    return total


def classificar_risco(graus_hora):
    """Traduz os graus-hora acumulados em um dos quatro niveis de risco."""
    if graus_hora < LIMITE_AMARELO:
        return "VERDE"
    if graus_hora < LIMITE_LARANJA:
        return "AMARELO"
    if graus_hora < LIMITE_VERMELHO:
        return "LARANJA"
    return "VERMELHO"


def detectar_eventos_porta(leituras):
    """Junta leituras seguidas com porta aberta em um unico evento."""
    eventos = []
    evento_atual = None
    for leitura in leituras:
        if porta_aberta(leitura["luminosidade_lux"]):
            if evento_atual is None:
                evento_atual = {
                    "inicio": leitura["data_hora"],
                    "fim": leitura["data_hora"],
                    "lux_max": leitura["luminosidade_lux"],
                }
            else:
                evento_atual["fim"] = leitura["data_hora"]
                evento_atual["lux_max"] = max(evento_atual["lux_max"], leitura["luminosidade_lux"])
        elif evento_atual is not None:
            eventos.append(evento_atual)
            evento_atual = None

    if evento_atual is not None:
        eventos.append(evento_atual)

    for evento in eventos:
        segundos = (evento["fim"] - evento["inicio"]).total_seconds()
        evento["duracao_min"] = round(segundos / 60, 1)
    return eventos


def limpar_leituras(leituras):
    """
    Ordena por horario, tira leituras com temperatura invalida e
    retransmissoes (duas leituras com o mesmo horario).
    """
    ordenadas = sorted(leituras, key=lambda leitura: leitura["data_hora"])
    limpas = []
    for leitura in ordenadas:
        if not temperatura_valida(leitura["temperatura_c"]):
            continue
        if limpas and limpas[-1]["data_hora"] == leitura["data_hora"]:
            continue
        limpas.append(leitura)
    return limpas


def analisar_lote(leituras, faixa):
    """
    Monta a analise completa de um lote.

    faixa e um dicionario com temp_min_c, temp_max_c,
    umidade_min_pct e umidade_max_pct da fruta do lote.
    """
    leituras = limpar_leituras(leituras)

    if not leituras:
        return {
            "amostras": 0,
            "amostras_fora_faixa": 0,
            "primeira_leitura": None,
            "ultima_leitura": None,
            "temp_min_c": None,
            "temp_max_c": None,
            "temp_media_c": None,
            "graus_hora": 0.0,
            "nivel": "SEM_DADOS",
            "recomendacao": RECOMENDACOES["SEM_DADOS"],
            "eventos_porta": [],
        }

    temperaturas = [leitura["temperatura_c"] for leitura in leituras]
    fora_faixa = 0
    for temperatura in temperaturas:
        if fora_da_faixa(temperatura, faixa["temp_min_c"], faixa["temp_max_c"]):
            fora_faixa += 1

    graus_hora = calcular_graus_hora(leituras, faixa["temp_max_c"])
    nivel = classificar_risco(graus_hora)

    return {
        "amostras": len(leituras),
        "amostras_fora_faixa": fora_faixa,
        "primeira_leitura": leituras[0]["data_hora"],
        "ultima_leitura": leituras[-1]["data_hora"],
        "temp_min_c": min(temperaturas),
        "temp_max_c": max(temperaturas),
        "temp_media_c": round(sum(temperaturas) / len(temperaturas), 2),
        "graus_hora": round(graus_hora, 2),
        "nivel": nivel,
        "recomendacao": RECOMENDACOES[nivel],
        "eventos_porta": detectar_eventos_porta(leituras),
    }
