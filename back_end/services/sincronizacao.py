"""Copia as leituras novas do ThingSpeak para o banco local."""

from datetime import timedelta
from os import getenv
from threading import Lock

from config import CANAL_THINGSPEAK, CHAVE_LEITURA_THINGSPEAK
from models.tabelas import Dispositivo, Leitura, LeituraDispositivo, Lote, VinculoDispositivo
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
from services.datas import agora_utc, para_utc
from services.erros import ErroThingSpeak

# Leituras podem chegar atrasadas e fora de ordem, com o horario da medicao.
# Por isso a busca volta alguns dias antes da ultima leitura gravada: cobre uma
# viagem inteira guardada no sensor. Quem ja esta gravado nao e gravado de novo.
MARGEM_DE_ATRASO = timedelta(days=7)

# Leitura com horario depois de agora + esta folga vem de relogio errado no sensor.
# A folga aceita a pequena diferenca normal entre o relogio dele e o nosso.
FOLGA_DO_RELOGIO = timedelta(minutes=5)
trava_sincronizacao = Lock()


def consultar_leituras(sessao, dispositivo_id):
    if dispositivo_id is None:
        return sessao.query(Leitura), Leitura
    consulta = sessao.query(LeituraDispositivo).filter_by(dispositivo_id=dispositivo_id)
    return consulta, LeituraDispositivo


def limite_do_relogio():
    return agora_utc() + FOLGA_DO_RELOGIO


def inicio_da_busca(sessao, dispositivo_id):
    """De onde buscar no ThingSpeak. Banco vazio (None): busca tudo."""
    # Ignora leitura com horario no futuro: a busca pularia para depois das reais.
    consulta, modelo = consultar_leituras(sessao, dispositivo_id)
    consulta = consulta.filter(modelo.data_hora <= limite_do_relogio())
    ultima = consulta.order_by(modelo.data_hora.desc()).first()
    if ultima is None:
        if dispositivo_id is not None:
            primeiro = sessao.query(Lote.inicio).join(VinculoDispositivo).filter(
                VinculoDispositivo.dispositivo_id == dispositivo_id,
            ).order_by(Lote.inicio).first()
            if primeiro is not None:
                return primeiro.inicio
        return None
    return ultima.data_hora - MARGEM_DE_ATRASO


def leitura_aproveitavel(leitura, limite):
    """Descarta temperatura invalida e horario depois do limite (relogio errado)."""
    if not temperatura_valida(leitura["temperatura_c"]):
        return False
    return para_utc(leitura["data_hora"]) <= limite


def gravar_leitura(sessao, leitura, dispositivo_id):
    dados = dict(
        entry_id=leitura["entry_id"],
        data_hora=para_utc(leitura["data_hora"]),
        temperatura_c=leitura["temperatura_c"],
        umidade_pct=valor_na_faixa_ou_nulo(leitura["umidade_pct"], UMIDADE_MIN, UMIDADE_MAX),
        luminosidade_lux=valor_na_faixa_ou_nulo(leitura["luminosidade_lux"], LUX_MIN, LUX_MAX),
    )
    if dispositivo_id is None:
        sessao.add(Leitura(**dados))
    else:
        sessao.add(LeituraDispositivo(dispositivo_id=dispositivo_id, **dados))


def sincronizar_canal(sessao, canal, chave_leitura, dispositivo_id=None):
    """
    Busca as leituras do canal e grava as que ainda nao existem.
    A chave de comparacao e o entry_id do ThingSpeak, entao chamar
    varias vezes nao duplica nada.
    """
    recebidas = thingspeak.buscar_leituras(
        canal, desde=inicio_da_busca(sessao, dispositivo_id), chave_leitura=chave_leitura,
    )
    consulta, modelo = consultar_leituras(sessao, dispositivo_id)
    gravados = {entrada for (entrada,) in consulta.with_entities(modelo.entry_id)}
    limite = limite_do_relogio()

    novas = 0
    descartadas = 0
    for leitura in recebidas:
        if not leitura_aproveitavel(leitura, limite):
            descartadas += 1
        elif leitura["entry_id"] not in gravados:
            gravar_leitura(sessao, leitura, dispositivo_id)
            gravados.add(leitura["entry_id"])
            novas += 1

    sessao.commit()
    return {
        "canal": canal,
        "recebidas": len(recebidas),
        "novas": novas,
        "descartadas": descartadas,
    }


def sincronizar(sessao):
    # O servidor local usa um processo; a trava mantém dois cliques simultâneos
    # de competirem pelas mesmas leituras. Cada tabela também tem chave única.
    with trava_sincronizacao:
        return sincronizar_placas(sessao)


def sincronizar_placas(sessao):
    ids_vinculados = sessao.query(VinculoDispositivo.dispositivo_id)
    placas = sessao.query(Dispositivo).filter(Dispositivo.id.in_(ids_vinculados.statement)).order_by(
        Dispositivo.id,
    ).all()
    conflito_padrao = sessao.query(Dispositivo).filter_by(canal=CANAL_THINGSPEAK).first() is not None
    if not placas and not conflito_padrao:
        return sincronizar_canal(sessao, CANAL_THINGSPEAK, CHAVE_LEITURA_THINGSPEAK)

    canais = []
    falhas = []
    if conflito_padrao:
        falhas.append({"canal": CANAL_THINGSPEAK, "mensagem": "Canal padrão em conflito com uma placa cadastrada."})
    else:
        try:
            canais.append(sincronizar_canal(sessao, CANAL_THINGSPEAK, CHAVE_LEITURA_THINGSPEAK))
        except ErroThingSpeak:
            falhas.append({"canal": CANAL_THINGSPEAK, "mensagem": "Não foi possível ler o canal padrão."})
    for placa in placas:
        chave = getenv(f"THINGSPEAK_CHAVE_LEITURA_{placa.canal}")
        try:
            canais.append(sincronizar_canal(sessao, placa.canal, chave, placa.id))
        except ErroThingSpeak:
            falhas.append({"canal": placa.canal, "mensagem": "Não foi possível ler o canal da placa."})
    if not canais:
        raise ErroThingSpeak("Não foi possível sincronizar nenhum canal.")
    return {
        "canal": CANAL_THINGSPEAK,
        "recebidas": sum(c["recebidas"] for c in canais),
        "novas": sum(c["novas"] for c in canais),
        "descartadas": sum(c["descartadas"] for c in canais),
        "canais": canais,
        "falhas": falhas,
    }
