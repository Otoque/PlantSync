"""Copia as leituras novas do ThingSpeak para o banco local."""

from config import CANAL_THINGSPEAK, THINGSPEAK_READ_API_KEY
from models.tabelas import Leitura
from services import thingspeak
from services.analise import temperatura_valida
from services.datas import para_utc


def sincronizar(sessao):
    """
    Busca as leituras do canal e grava as que ainda nao existem.
    A chave de comparacao e o entry_id do ThingSpeak, entao chamar
    varias vezes nao duplica nada.
    """
    recebidas = thingspeak.buscar_leituras(CANAL_THINGSPEAK, read_api_key=THINGSPEAK_READ_API_KEY)

    ids_gravados = set()
    for (entry_id,) in sessao.query(Leitura.entry_id).all():
        ids_gravados.add(entry_id)

    novas = 0
    descartadas = 0
    for leitura in recebidas:
        if not temperatura_valida(leitura["temperatura_c"]):
            descartadas += 1
            continue
        if leitura["entry_id"] in ids_gravados:
            continue

        sessao.add(Leitura(
            entry_id=leitura["entry_id"],
            data_hora=para_utc(leitura["data_hora"]),
            temperatura_c=leitura["temperatura_c"],
            umidade_pct=leitura["umidade_pct"],
            luminosidade_lux=leitura["luminosidade_lux"],
        ))
        ids_gravados.add(leitura["entry_id"])
        novas += 1

    sessao.commit()
    return {
        "canal": CANAL_THINGSPEAK,
        "recebidas": len(recebidas),
        "novas": novas,
        "descartadas": descartadas,
    }
