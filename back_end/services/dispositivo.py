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

logger = logging.getLogger("plantsync")


def chave_tem_tamanho_minimo(chave):
    """Uma chave so de espacos nao conta como chave longa."""
    if not chave:
        return False
    return len(chave.strip()) >= TAMANHO_MINIMO_DA_CHAVE


def avisar_se_a_chave_for_invalida(chave):
    """Chamada ao ligar o servidor. O aviso nunca mostra a chave."""
    if not chave_tem_tamanho_minimo(chave):
        logger.warning(
            "PLANTSYNC_CHAVE_DISPOSITIVO nao foi definida ou tem menos de %s caracteres: "
            "GET /api/dispositivo/faixa vai responder 503.",
            TAMANHO_MINIMO_DA_CHAVE,
        )


def conferir_chave(recebida, configurada):
    """Levanta um erro se o servidor nao tiver chave ou se a recebida nao for igual a ela."""
    if not chave_tem_tamanho_minimo(configurada):
        raise ErroDispositivoNaoConfigurado("Chave do dispositivo não configurada no servidor.")
    if recebida is None:
        raise ErroChaveDoDispositivo("Chave do dispositivo inválida.")
    # Em bytes porque compare_digest recusa texto com acento. Ele leva o mesmo
    # tempo mesmo se as chaves diferem logo no comeco.
    if not hmac.compare_digest(recebida.encode("utf-8"), configurada.encode("utf-8")):
        raise ErroChaveDoDispositivo("Chave do dispositivo inválida.")


def faixa_para_a_placa(sessao):
    """Faixa copiada no lote em transito (ha um so por canal)."""
    lote = lote_em_transito(sessao)
    if lote is None:
        raise ErroNaoEncontrado("Nenhum lote em trânsito.")

    resposta = {"lote_id": lote.id, "fruta": lote.fruta_id}
    resposta.update(faixa_do_lote(lote))
    return resposta
