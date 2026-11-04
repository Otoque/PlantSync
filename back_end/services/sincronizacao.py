"""Copia as leituras novas do ThingSpeak para o banco local."""

from datetime import timedelta

from config import CANAL_THINGSPEAK, CHAVE_LEITURA_THINGSPEAK
from models.tabelas import Leitura
# Importamos o modulo (e nao a funcao) para os testes poderem trocar
# thingspeak.buscar_leituras por uma versao falsa, sem internet.
from services import thingspeak
from services.analise import (
    LUX_MAX,
    LUX_MIN,
    UMIDADE_MAX,
    UMIDADE_MIN,
    temperatura_valida,
    valor_na_faixa_ou_nulo,
)
from services.datas import para_utc

# Leituras podem chegar atrasadas e fora de ordem, com o horario da medicao.
# Por isso a busca volta alguns dias antes da ultima leitura gravada: cobre uma
# viagem inteira guardada no sensor. Quem ja esta gravado nao e gravado de novo.
MARGEM_DE_ATRASO = timedelta(days=7)


def ids_ja_gravados(sessao):
    """Conjunto com o entry_id de todas as leituras que ja estao no banco."""
    ids = set()
    for leitura in sessao.query(Leitura).all():
        ids.add(leitura.entry_id)
    return ids


def inicio_da_busca(sessao):
    """De onde buscar no ThingSpeak. Banco vazio (None): busca tudo."""
    ultima = sessao.query(Leitura).order_by(Leitura.data_hora.desc()).first()
    if ultima is None:
        return None
    return ultima.data_hora - MARGEM_DE_ATRASO


def gravar_leitura(sessao, leitura):
    sessao.add(Leitura(
        entry_id=leitura["entry_id"],
        data_hora=para_utc(leitura["data_hora"]),
        temperatura_c=leitura["temperatura_c"],
        umidade_pct=valor_na_faixa_ou_nulo(leitura["umidade_pct"], UMIDADE_MIN, UMIDADE_MAX),
        luminosidade_lux=valor_na_faixa_ou_nulo(leitura["luminosidade_lux"], LUX_MIN, LUX_MAX),
    ))


def sincronizar(sessao):
    """
    Busca as leituras do canal e grava as que ainda nao existem.
    A chave de comparacao e o entry_id do ThingSpeak, entao chamar
    varias vezes nao duplica nada.
    """
    recebidas = thingspeak.buscar_leituras(
        CANAL_THINGSPEAK,
        desde=inicio_da_busca(sessao),
        chave_leitura=CHAVE_LEITURA_THINGSPEAK,
    )
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
