"""Monta os alertas que o painel mostra para os lotes em transito."""

from models.tabelas import Lote
from services.analise import ACOES_CURTAS
from services.datas import formatar_utc, hora_recife
from services.lotes import analisar

# Quanto maior, mais grave. Usado para ordenar a lista de alertas.
GRAVIDADE = {"AMARELO": 1, "LARANJA": 2, "VERMELHO": 3}


def alerta_risco_termico(lote, analise):
    mensagem = (
        f"Lote {lote.id} ({lote.fruta_id}) acumulou {analise['graus_hora']:.0f} °C·h "
        f"acima de {lote.temp_max_c:g} °C: {ACOES_CURTAS[analise['nivel']]}."
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
    alertas = []
    lotes = sessao.query(Lote).filter(Lote.fim.is_(None)).all()

    for lote in lotes:
        analise = analisar(sessao, lote)
        if analise["nivel"] in GRAVIDADE:
            alertas.append(alerta_risco_termico(lote, analise))
        for evento in analise["eventos_porta"]:
            alertas.append(alerta_porta_aberta(lote, evento))

    # Mais grave primeiro; no mesmo nivel, o mais recente primeiro.
    alertas.sort(key=lambda alerta: alerta["data_hora"], reverse=True)
    alertas.sort(key=lambda alerta: GRAVIDADE[alerta["nivel"]], reverse=True)

    for alerta in alertas:
        alerta["data_hora"] = formatar_utc(alerta["data_hora"])
    return alertas
