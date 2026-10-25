"""Regras dos lotes: leituras do lote, analise e formato de resposta."""

from models.tabelas import Leitura, Lote
from services.analise import analisar_lote, fora_da_faixa, limpar_leituras, porta_aberta
from services.datas import formatar_utc


def lote_em_transito(sessao):
    """Devolve o lote que ainda nao foi encerrado, ou None."""
    return sessao.query(Lote).filter(Lote.fim.is_(None)).first()


def faixa_do_lote(lote):
    return {
        "temp_min_c": lote.temp_min_c,
        "temp_max_c": lote.temp_max_c,
        "umidade_min_pct": lote.umidade_min_pct,
        "umidade_max_pct": lote.umidade_max_pct,
    }


def leituras_do_lote(sessao, lote):
    """
    Uma leitura pertence ao lote quando o horario dela esta entre o
    inicio e o fim do lote. Lote sem fim recebe tudo depois do inicio.
    """
    consulta = sessao.query(Leitura).filter(Leitura.data_hora >= lote.inicio)
    if lote.fim is not None:
        consulta = consulta.filter(Leitura.data_hora <= lote.fim)
    leituras = consulta.order_by(Leitura.data_hora).all()

    # O servico de analise trabalha com dicionarios simples.
    lista = []
    for leitura in leituras:
        lista.append({
            "data_hora": leitura.data_hora,
            "temperatura_c": leitura.temperatura_c,
            "umidade_pct": leitura.umidade_pct,
            "luminosidade_lux": leitura.luminosidade_lux,
        })
    return limpar_leituras(lista)


def analisar(sessao, lote):
    return analisar_lote(leituras_do_lote(sessao, lote), faixa_do_lote(lote))


def lote_para_json(lote, analise):
    """Formato curto, usado na lista de lotes."""
    if lote.fim is None:
        status = "em_transito"
    else:
        status = "encerrado"

    return {
        "id": lote.id,
        "fruta": lote.fruta_id,
        "origem": lote.origem,
        "porto_destino": lote.porto_destino,
        "inicio": formatar_utc(lote.inicio),
        "fim": formatar_utc(lote.fim),
        "status": status,
        "faixa_segura": faixa_do_lote(lote),
        "risco": {
            "nivel": analise["nivel"],
            "graus_hora": analise["graus_hora"],
        },
    }


def lote_detalhado_json(lote, analise):
    """Formato completo: o lote com toda a analise da viagem."""
    resposta = lote_para_json(lote, analise)
    del resposta["risco"]

    eventos = []
    for evento in analise["eventos_porta"]:
        eventos.append({
            "inicio": formatar_utc(evento["inicio"]),
            "fim": formatar_utc(evento["fim"]),
            "duracao_min": evento["duracao_min"],
            "lux_max": evento["lux_max"],
        })

    resposta["analise"] = {
        "amostras": analise["amostras"],
        "amostras_fora_faixa": analise["amostras_fora_faixa"],
        "primeira_leitura": formatar_utc(analise["primeira_leitura"]),
        "ultima_leitura": formatar_utc(analise["ultima_leitura"]),
        "temp_min_c": analise["temp_min_c"],
        "temp_max_c": analise["temp_max_c"],
        "temp_media_c": analise["temp_media_c"],
        "graus_hora": analise["graus_hora"],
        "nivel": analise["nivel"],
        "recomendacao": analise["recomendacao"],
        "eventos_porta": eventos,
    }
    return resposta


def leitura_para_json(leitura, faixa):
    return {
        "data_hora": formatar_utc(leitura["data_hora"]),
        "temperatura_c": leitura["temperatura_c"],
        "umidade_pct": leitura["umidade_pct"],
        "luminosidade_lux": leitura["luminosidade_lux"],
        "fora_faixa_temp": fora_da_faixa(leitura["temperatura_c"], faixa["temp_min_c"], faixa["temp_max_c"]),
        "fora_faixa_umidade": fora_da_faixa(leitura["umidade_pct"], faixa["umidade_min_pct"], faixa["umidade_max_pct"]),
        "porta_aberta": porta_aberta(leitura["luminosidade_lux"]),
    }
