"""Monta os alertas que o painel mostra para o lote em transito."""

from services.analise import ACOES_CURTAS, GRAVIDADE
from services.datas import formatar_utc, hora_recife
from services.lotes import buscar_e_analisar, lote_em_transito


def alerta_risco_termico(lote, analise):
    acao = ACOES_CURTAS[analise["nivel"]]
    # :.0f mostra os graus-hora sem casas decimais; :g tira o ".0" do limite (2.0 vira 2).
    mensagem = (
        f"Lote {lote.id} ({lote.fruta_id}) acumulou {analise['graus_hora']:.0f} °C·h "
        f"acima de {lote.temp_max_c:g} °C: {acao}."
    )
    return {
        "lote_id": lote.id,
        "fruta": lote.fruta_id,
        "tipo": "risco_termico",
        "nivel": analise["nivel"],
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
        "nivel": "AMARELO",
        "mensagem": mensagem,
        "data_hora": evento["inicio"],
    }


def gerar_alertas(sessao):
    """
    Alertas do lote em transito: um de risco termico (se o nivel nao for
    VERDE) e um para cada abertura de porta. Lote encerrado nao gera alerta.
    """
    lote = lote_em_transito(sessao)
    if lote is None:
        return []

    alertas = []
    analise = buscar_e_analisar(sessao, lote)
    if analise["nivel"] in GRAVIDADE:
        alertas.append(alerta_risco_termico(lote, analise))
    for evento in analise["eventos_porta"]:
        alertas.append(alerta_porta_aberta(lote, evento))

    # Mais grave primeiro; no mesmo nivel, o mais recente primeiro.
    alertas.sort(key=lambda alerta: (GRAVIDADE[alerta["nivel"]], alerta["data_hora"]), reverse=True)

    # A data so vira texto depois de ordenar, para ordenar por data e nao por texto.
    for alerta in alertas:
        alerta["data_hora"] = formatar_utc(alerta["data_hora"])
    return alertas
