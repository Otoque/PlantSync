"""
Analise da viagem de um lote: graus-hora, nivel de risco e aberturas de porta.

A logica foi trazida de analytics/eda_plantsync.py (funcoes enriquecer,
classificar_carga e detectar_eventos_porta), reescrita sem pandas para a API
ficar leve. Se um limiar mudar aqui, mude tambem no pipeline analitico.

Diferencas em relacao ao pipeline: aqui os graus-hora sao contados nos DOIS
lados da faixa (calor acima do teto e frio abaixo do piso; na manga, o frio
abaixo do piso causa corte negro) e cada intervalo usa a media das suas duas
pontas (ver docs/api-contrato.md).

Cada leitura e um dicionario com as chaves:
    data_hora (datetime), temperatura_c, umidade_pct, luminosidade_lux

Atencao aos nomes: na "faixa", temp_min_c e temp_max_c sao os LIMITES seguros
da fruta; no resultado da analise, sao a menor e a maior temperatura MEDIDAS.
Os nomes seguem o contrato da API (docs/api-contrato.md).
Nas funcoes, piso = temp_min_c da faixa e teto = temp_max_c da faixa.
"""

from models.limites import TEMP_FISICA_MAX, TEMP_FISICA_MIN

# Luz acima disso dentro do compartimento lacrado indica porta aberta.
LUX_PORTA_ABERTA = 300.0

# Limites para aceitar umidade e luz. Luz do sol direto fica perto de 100 mil lux.
UMIDADE_MIN = 0.0
UMIDADE_MAX = 100.0
LUX_MIN = 0.0
LUX_MAX = 200000.0

# Limiares de graus-hora definidos pela equipe no pipeline analitico.
# Ainda precisam ser validados com um produtor parceiro.
# Valem igualmente para o lado quente e para o lado frio.
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

# Quanto maior o numero, mais grave. VERDE e SEM_DADOS (0) nao geram alerta.
GRAVIDADE = {"SEM_DADOS": 0, "VERDE": 0, "AMARELO": 1, "LARANJA": 2, "VERMELHO": 3}


def temperatura_valida(temperatura):
    """Diz se a temperatura pode entrar na analise."""
    if temperatura is None:
        return False
    return TEMP_FISICA_MIN <= temperatura <= TEMP_FISICA_MAX


def valor_na_faixa_ou_nulo(valor, minimo, maximo):
    """
    Devolve o valor se ele estiver na faixa; senao, None. Infinito e NaN (que
    o ThingSpeak pode mandar como texto, ex.: "1e999") tambem viram None,
    porque qualquer comparacao com NaN da falso.
    """
    if valor is None:
        return None
    if minimo <= valor <= maximo:
        return valor
    return None


def porta_aberta(luminosidade):
    """Sem medida de luz (None) nao conta como porta aberta."""
    if luminosidade is None:
        return False
    return luminosidade > LUX_PORTA_ABERTA


def fora_da_faixa(valor, minimo, maximo):
    """Sem medida (None) nao conta como fora da faixa."""
    if valor is None:
        return False
    return valor < minimo or valor > maximo


def lado_da_faixa(temperatura, piso, teto):
    """Devolve "acima" (calor), "abaixo" (frio) ou None (dentro da faixa)."""
    if temperatura > teto:
        return "acima"
    if temperatura < piso:
        return "abaixo"
    return None


def calcular_graus_hora(leituras, piso, teto):
    """
    Soma, separados, o calor acima do teto e o frio abaixo do piso,
    cada um multiplicado pelo tempo. Devolve os dois: (acima, abaixo).

    Em cada intervalo entre duas leituras, vale a media do excesso nas duas
    pontas. Assim, esfriar de 30 para 1 grau soma o mesmo que esquentar de 1
    para 30. As leituras devem vir em ordem. Leitura no limite tem excesso zero.
    """
    acima = 0.0
    abaixo = 0.0
    anterior = None
    for leitura in leituras:
        if anterior is not None:
            intervalo_h = (leitura["data_hora"] - anterior["data_hora"]).total_seconds() / 3600
            calor_antes = max(0.0, anterior["temperatura_c"] - teto)
            calor_agora = max(0.0, leitura["temperatura_c"] - teto)
            frio_antes = max(0.0, piso - anterior["temperatura_c"])
            frio_agora = max(0.0, piso - leitura["temperatura_c"])
            acima += (calor_antes + calor_agora) / 2 * intervalo_h
            abaixo += (frio_antes + frio_agora) / 2 * intervalo_h
        anterior = leitura
    return acima, abaixo


def classificar_risco(graus_hora):
    """Traduz os graus-hora acumulados em um dos quatro niveis de risco."""
    if graus_hora < LIMITE_AMARELO:
        return "VERDE"
    if graus_hora < LIMITE_LARANJA:
        return "AMARELO"
    if graus_hora < LIMITE_VERMELHO:
        return "LARANJA"
    return "VERMELHO"


def nivel_mais_grave(nivel_a, nivel_b):
    """O pior dos dois niveis. Calor e frio nao se compensam."""
    if GRAVIDADE[nivel_a] >= GRAVIDADE[nivel_b]:
        return nivel_a
    return nivel_b


def duracao_em_minutos(inicio, fim):
    return round((fim - inicio).total_seconds() / 60, 1)


def maior_buraco_em_minutos(leituras, inicio, fim):
    """
    Maior tempo sem leitura entre o inicio e o fim do lote, contando tambem
    do inicio ate a primeira leitura e da ultima ate o fim.
    As leituras devem vir limpas e em ordem.
    """
    maior = 0.0
    anterior = inicio
    for leitura in leituras:
        maior = max(maior, duracao_em_minutos(anterior, leitura["data_hora"]))
        anterior = leitura["data_hora"]
    return max(maior, duracao_em_minutos(anterior, fim))


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
        evento["duracao_min"] = duracao_em_minutos(evento["inicio"], evento["fim"])
    return eventos


def novo_trecho(leitura, lado):
    """Abre um trecho fora da faixa a partir de uma leitura."""
    return {
        "inicio": leitura["data_hora"],
        "fim": leitura["data_hora"],
        "lado": lado,
        "temp_extrema_c": leitura["temperatura_c"],
    }


def atualizar_trecho(trecho, leitura):
    """
    Estende o trecho ate a leitura e guarda a temperatura mais distante
    da faixa: a maior, se o trecho e de calor; a menor, se e de frio.
    """
    trecho["fim"] = leitura["data_hora"]
    temperatura = leitura["temperatura_c"]
    if trecho["lado"] == "acima":
        trecho["temp_extrema_c"] = max(trecho["temp_extrema_c"], temperatura)
    else:
        trecho["temp_extrema_c"] = min(trecho["temp_extrema_c"], temperatura)


def detectar_trechos_fora_da_faixa(leituras, piso, teto):
    """Junta leituras seguidas do mesmo lado da faixa (calor ou frio) em um trecho."""
    trechos = []
    trecho_atual = None
    for leitura in leituras:
        lado = lado_da_faixa(leitura["temperatura_c"], piso, teto)

        if trecho_atual is not None and lado == trecho_atual["lado"]:
            atualizar_trecho(trecho_atual, leitura)
        else:
            # Mudou de lado ou voltou para a faixa: fecha o trecho aberto.
            if trecho_atual is not None:
                trechos.append(trecho_atual)
            trecho_atual = None
            if lado is not None:
                trecho_atual = novo_trecho(leitura, lado)

    if trecho_atual is not None:
        trechos.append(trecho_atual)

    for trecho in trechos:
        trecho["duracao_min"] = duracao_em_minutos(trecho["inicio"], trecho["fim"])
    return trechos


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


def analise_sem_dados():
    """Resultado de um lote que ainda nao recebeu nenhuma leitura."""
    return {
        "amostras": 0,
        "amostras_fora_faixa": 0,
        "primeira_leitura": None,
        "ultima_leitura": None,
        "temp_min_c": None,
        "temp_max_c": None,
        "temp_media_c": None,
        "graus_hora_acima": 0.0,
        "graus_hora_abaixo": 0.0,
        "nivel_acima": "SEM_DADOS",
        "nivel_abaixo": "SEM_DADOS",
        "nivel": "SEM_DADOS",
        "recomendacao": RECOMENDACOES["SEM_DADOS"],
        "trechos_fora_faixa": [],
        "eventos_porta": [],
    }


def resumo_das_temperaturas(leituras, faixa):
    """Contagens e temperaturas medidas (menor, maior e media) da viagem."""
    temperaturas = []
    fora_faixa = 0
    for leitura in leituras:
        temperatura = leitura["temperatura_c"]
        temperaturas.append(temperatura)
        if fora_da_faixa(temperatura, faixa["temp_min_c"], faixa["temp_max_c"]):
            fora_faixa += 1

    return {
        "amostras": len(leituras),
        "amostras_fora_faixa": fora_faixa,
        "primeira_leitura": leituras[0]["data_hora"],
        "ultima_leitura": leituras[-1]["data_hora"],
        "temp_min_c": min(temperaturas),
        "temp_max_c": max(temperaturas),
        "temp_media_c": round(sum(temperaturas) / len(temperaturas), 2),
    }


def analisar_lote(leituras, faixa):
    """
    Monta a analise completa de um lote.

    faixa e um dicionario com temp_min_c, temp_max_c,
    umidade_min_pct e umidade_max_pct da fruta do lote.
    """
    leituras = limpar_leituras(leituras)
    if not leituras:
        return analise_sem_dados()

    piso = faixa["temp_min_c"]
    teto = faixa["temp_max_c"]
    acima, abaixo = calcular_graus_hora(leituras, piso, teto)
    nivel_acima = classificar_risco(acima)
    nivel_abaixo = classificar_risco(abaixo)
    nivel = nivel_mais_grave(nivel_acima, nivel_abaixo)

    analise = resumo_das_temperaturas(leituras, faixa)
    analise["graus_hora_acima"] = round(acima, 2)
    analise["graus_hora_abaixo"] = round(abaixo, 2)
    analise["nivel_acima"] = nivel_acima
    analise["nivel_abaixo"] = nivel_abaixo
    analise["nivel"] = nivel
    analise["recomendacao"] = RECOMENDACOES[nivel]
    analise["trechos_fora_faixa"] = detectar_trechos_fora_da_faixa(leituras, piso, teto)
    analise["eventos_porta"] = detectar_eventos_porta(leituras)
    return analise
