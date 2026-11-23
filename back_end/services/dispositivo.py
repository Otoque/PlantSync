"""
O que a placa busca na API: a faixa segura do lote em transito, para acender o LED
a vista do motorista. A placa usa uma chave propria, separada do login do painel, e
recebe so o necessario: nada de token, produtor ou leituras.
"""

import hmac
import logging

from services.erros import (
    ErroChaveDoDispositivo,
    ErroDispositivoNaoConfigurado,
    ErroNaoEncontrado,
)
from services.lotes import faixa_do_lote, lote_em_transito

TAMANHO_MINIMO_DA_CHAVE = 32
MENSAGEM_CHAVE_INVALIDA = "Chave do dispositivo inválida."

logger = logging.getLogger("plantsync")


def chave_e_valida(chave):
    """
    A chave precisa ter o tamanho minimo, sem contar espacos nas pontas, e so
    caracteres sem acento: o servidor le os cabecalhos como latin-1, entao uma
    chave com acento nunca conferiria, mesmo com a placa enviando a chave certa.
    """
    if not chave or not chave.isascii():
        return False
    return len(chave.strip()) >= TAMANHO_MINIMO_DA_CHAVE


def avisar_se_a_chave_for_invalida(chave):
    """Chamada ao ligar o servidor. O aviso nunca mostra a chave."""
    if not chave_e_valida(chave):
        logger.warning(
            "PLANTSYNC_CHAVE_DISPOSITIVO nao foi definida, tem acento ou tem menos de %s "
            "caracteres: GET /api/dispositivo/faixa vai responder 503.",
            TAMANHO_MINIMO_DA_CHAVE,
        )


def conferir_chave(recebida, configurada):
    """Levanta um erro se o servidor nao tiver chave ou se a recebida nao for igual a ela."""
    if not chave_e_valida(configurada):
        raise ErroDispositivoNaoConfigurado("Chave do dispositivo não configurada no servidor.")
    if recebida is None:
        raise ErroChaveDoDispositivo(MENSAGEM_CHAVE_INVALIDA)
    # Em bytes porque compare_digest recusa texto com acento. Ele leva o mesmo
    # tempo mesmo se as chaves diferem logo no comeco.
    if not hmac.compare_digest(recebida.encode("utf-8"), configurada.encode("utf-8")):
        raise ErroChaveDoDispositivo(MENSAGEM_CHAVE_INVALIDA)


def faixa_para_a_placa(sessao):
    """A credencial antiga dá acesso somente à faixa da placa padrão."""
    from models.migracoes import RegistroMigracao
    convertido = sessao.get(RegistroMigracao, "legado_para_operacao_v1")
    if convertido is not None:
        return faixa_operacional(sessao, convertido.empresa_id)
    lote = lote_em_transito(sessao)
    if lote is None:
        raise ErroNaoEncontrado("Nenhum lote em trânsito.")

    resposta = {"lote_id": lote.id, "fruta": lote.fruta_id}
    resposta.update(faixa_do_lote(lote))
    return resposta


def faixa_operacional(sessao, empresa_id):
    from fastapi import HTTPException
    from sqlalchemy import or_, select

    from config import CANAL_THINGSPEAK
    from models.operacao import FonteSensor, LoteOperacional, Permanencia, VinculoSensor
    from services.datas import agora_utc

    agora = agora_utc()
    consulta = select(LoteOperacional).join(
        Permanencia, Permanencia.lote_id == LoteOperacional.id,
    ).join(
        VinculoSensor, VinculoSensor.ambiente_id == Permanencia.ambiente_id,
    ).join(FonteSensor, FonteSensor.id == VinculoSensor.fonte_id).where(
        FonteSensor.empresa_id == empresa_id,
        FonteSensor.canal == CANAL_THINGSPEAK,
        Permanencia.inicio <= agora,
        or_(Permanencia.fim.is_(None), Permanencia.fim > agora),
        VinculoSensor.inicio <= agora,
        or_(VinculoSensor.fim.is_(None), VinculoSensor.fim > agora),
        LoteOperacional.fase < 3,
    ).distinct()
    lotes = list(sessao.scalars(consulta))
    if not lotes:
        raise ErroNaoEncontrado("Nenhum lote monitorado pela placa padrão.")
    if len(lotes) != 1:
        raise HTTPException(409, "A placa acompanha vários lotes. Consulte as faixas pela API da operação.")
    lote = lotes[0]
    return {"lote_id": lote.id, "fruta": lote.fruta_id, **faixa_do_lote(lote)}
