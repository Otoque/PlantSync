"""Copia as leituras novas do ThingSpeak para o banco local."""

from config import CANAL_THINGSPEAK, CHAVE_LEITURA_THINGSPEAK
from models.tabelas import Leitura
# Importamos o modulo (e nao a funcao) para os testes poderem trocar
# thingspeak.buscar_leituras por uma versao falsa, sem internet.
from services import thingspeak
from services.analise import temperatura_valida
from services.datas import para_utc


def ids_ja_gravados(sessao):
    """Conjunto com o entry_id de todas as leituras que ja estao no banco."""
    ids = set()
    for leitura in sessao.query(Leitura).all():
        ids.add(leitura.entry_id)
    return ids


def gravar_leitura(sessao, leitura):
    sessao.add(Leitura(
        entry_id=leitura["entry_id"],
        data_hora=para_utc(leitura["data_hora"]),
        temperatura_c=leitura["temperatura_c"],
        umidade_pct=leitura["umidade_pct"],
        luminosidade_lux=leitura["luminosidade_lux"],
    ))


def sincronizar(sessao):
    """
    Busca as leituras do canal e grava as que ainda nao existem.
    A chave de comparacao e o entry_id do ThingSpeak, entao chamar
    varias vezes nao duplica nada.
    """
    recebidas = thingspeak.buscar_leituras(CANAL_THINGSPEAK, chave_leitura=CHAVE_LEITURA_THINGSPEAK)
    gravados = ids_ja_gravados(sessao)

    novas = 0
    descartadas = 0
    for leitura in recebidas:
        if not temperatura_valida(leitura["temperatura_c"]):
            descartadas += 1
        elif leitura["entry_id"] not in gravados:
            gravar_leitura(sessao, leitura)
            gravados.add(leitura["entry_id"])
            novas += 1

    sessao.commit()
    return {
        "canal": CANAL_THINGSPEAK,
        "recebidas": len(recebidas),
        "novas": novas,
        "descartadas": descartadas,
    }
