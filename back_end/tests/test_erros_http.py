"""Confere o codigo HTTP e o corpo que cada erro dos services recebe no app.py."""

import json

import pytest

from app import (
    tratar_dispositivo_nao_configurado,
    tratar_erro_de_regra,
    tratar_erro_thingspeak,
    tratar_chave_do_dispositivo,
    tratar_nao_autenticado,
    tratar_nao_encontrado,
)
from services.erros import (
    ErroChaveDoDispositivo,
    ErroDeRegra,
    ErroDispositivoNaoConfigurado,
    ErroNaoAutenticado,
    ErroNaoEncontrado,
    ErroThingSpeak,
)


@pytest.mark.parametrize(
    "tratador, erro, codigo",
    [
        (tratar_erro_de_regra, ErroDeRegra, 400),
        (tratar_nao_autenticado, ErroNaoAutenticado, 401),
        (tratar_chave_do_dispositivo, ErroChaveDoDispositivo, 401),
        (tratar_dispositivo_nao_configurado, ErroDispositivoNaoConfigurado, 503),
        (tratar_nao_encontrado, ErroNaoEncontrado, 404),
        (tratar_erro_thingspeak, ErroThingSpeak, 502),
    ],
)
def test_erro_vira_o_codigo_http_documentado(tratador, erro, codigo):
    resposta = tratador(None, erro("mensagem de teste"))
    assert resposta.status_code == codigo
    assert json.loads(resposta.body) == {"erro": "mensagem de teste"}


def test_nao_autenticado_avisa_o_tipo_de_login():
    resposta = tratar_nao_autenticado(None, ErroNaoAutenticado("sem login"))
    assert resposta.headers["WWW-Authenticate"] == "Bearer"
