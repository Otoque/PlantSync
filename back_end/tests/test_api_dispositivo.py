"""
Testes de GET /api/dispositivo/faixa: a placa busca a faixa do lote em transito
para acender o LED, usando uma chave propria, separada do login.
"""

import logging

import pytest

from auxiliares import (
    ROTAS_PROTEGIDAS,
    corpo_de_lote,
    criar_lote,
    editar_fruta,
    encerrar_lote,
    faixa_da_uva,
)
from controllers import dispositivo as rotas_do_dispositivo
from services.dispositivo import avisar_se_a_chave_for_invalida

CHAVE = "chave-de-teste-com-mais-de-32-caracteres"
FAIXA = "/api/dispositivo/faixa"


# ---------- funcoes auxiliares deste arquivo ----------

def cabecalho_da_chave(chave=CHAVE):
    """Cabecalho que a placa envia."""
    return {"X-Chave-Dispositivo": chave}


def faixa_da_placa(placa, chave=CHAVE):
    """Busca a faixa como a placa faz. 'placa' e o cliente_sem_login."""
    return placa.get(FAIXA, headers=cabecalho_da_chave(chave))


def configurar_chave(monkeypatch, chave):
    """Faz de conta que o servidor ligou com esta PLANTSYNC_CHAVE_DISPOSITIVO."""
    # Troca no controller porque ele ja importou o valor de config.py ao carregar.
    monkeypatch.setattr(rotas_do_dispositivo, "PLANTSYNC_CHAVE_DISPOSITIVO", chave)


@pytest.fixture
def com_chave_configurada(monkeypatch):
    configurar_chave(monkeypatch, CHAVE)


# Nos testes abaixo, cliente (com login) so cria os lotes; cliente_sem_login faz o papel da placa.

# ---------- resposta ----------

def test_devolve_so_a_faixa_do_lote_em_transito(
    cliente, cliente_sem_login, com_chave_configurada
):
    lote = criar_lote(cliente)
    resposta = faixa_da_placa(cliente_sem_login)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "lote_id": lote["id"],
        "fruta": "uva",
        "temp_min_c": 0.0,
        "temp_max_c": 2.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 95.0,
    }


def test_usa_a_faixa_copiada_no_lote_e_nao_a_atual_da_fruta(
    cliente, cliente_sem_login, com_chave_configurada
):
    criar_lote(cliente)
    editar_fruta(cliente, "uva", temp_min_c=5.0, temp_max_c=9.0)
    resposta = faixa_da_placa(cliente_sem_login)
    assert resposta.json()["temp_max_c"] == 2.0


def test_usa_a_faixa_propria_do_lote(cliente, cliente_sem_login, com_chave_configurada):
    corpo = corpo_de_lote(faixa_segura=faixa_da_uva(temp_max_c=3.5))
    assert cliente.post("/api/lotes", json=corpo).status_code == 201
    resposta = faixa_da_placa(cliente_sem_login)
    assert resposta.json()["temp_max_c"] == 3.5


def test_sem_lote_em_transito_devolve_404(cliente_sem_login, com_chave_configurada):
    resposta = faixa_da_placa(cliente_sem_login)
    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "Nenhum lote em trânsito."}


def test_lote_encerrado_nao_conta_como_em_transito(
    cliente, cliente_sem_login, com_chave_configurada
):
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T20:00:00Z")
    assert faixa_da_placa(cliente_sem_login).status_code == 404


# ---------- chave do dispositivo ----------

def test_sem_chave_da_401(cliente_sem_login, com_chave_configurada):
    resposta = cliente_sem_login.get(FAIXA)
    assert resposta.status_code == 401
    assert resposta.json() == {"erro": "Chave do dispositivo inválida."}


def test_chave_errada_da_401(cliente_sem_login, com_chave_configurada):
    outra = "x" * len(CHAVE)
    assert faixa_da_placa(cliente_sem_login, outra).status_code == 401


def test_chave_com_acento_da_401_e_nao_derruba_a_api(cliente_sem_login, com_chave_configurada):
    # compare_digest recusa texto com acento; a comparacao precisa ser feita em bytes.
    cabecalho = {"X-Chave-Dispositivo": "chave-inválida".encode("latin-1")}
    assert cliente_sem_login.get(FAIXA, headers=cabecalho).status_code == 401


def test_sem_chave_valida_a_resposta_nao_revela_se_ha_lote(
    cliente, cliente_sem_login, com_chave_configurada
):
    # Sem lote em transito tambem e 401: o 404 so aparece para quem tem a chave.
    assert cliente_sem_login.get(FAIXA).status_code == 401
    criar_lote(cliente)
    assert cliente_sem_login.get(FAIXA).status_code == 401


def test_token_de_login_nao_abre_a_rota(cliente, com_chave_configurada):
    # O cliente padrao dos testes ja envia o token de login.
    criar_lote(cliente)
    assert cliente.get(FAIXA).status_code == 401


def test_chave_no_lugar_do_token_nao_abre_a_rota(cliente_sem_login, com_chave_configurada):
    cabecalho = {"Authorization": f"Bearer {CHAVE}"}
    assert cliente_sem_login.get(FAIXA, headers=cabecalho).status_code == 401


def test_chave_nao_abre_nenhuma_outra_rota(cliente_sem_login, com_chave_configurada):
    cabecalhos = {"X-Chave-Dispositivo": CHAVE, "Authorization": f"Bearer {CHAVE}"}
    for metodo, modelo_do_caminho in ROTAS_PROTEGIDAS:
        caminho = modelo_do_caminho.format(lote_id=1, fruta_id="uva")
        resposta = cliente_sem_login.request(metodo, caminho, headers=cabecalhos)
        assert resposta.status_code == 401, (metodo, caminho)


# ---------- chave nao configurada ----------

def test_sem_chave_configurada_da_503_mesmo_com_cabecalho(cliente_sem_login, monkeypatch):
    for chave_ruim in [None, "", "curta", " " * 40, "x" * 31]:
        configurar_chave(monkeypatch, chave_ruim)
        for cabecalhos in [None, cabecalho_da_chave(), cabecalho_da_chave("x" * 31)]:
            resposta = cliente_sem_login.get(FAIXA, headers=cabecalhos)
            assert resposta.status_code == 503, (chave_ruim, cabecalhos)
            assert resposta.json() == {"erro": "Chave do dispositivo não configurada no servidor."}


def test_chave_com_32_caracteres_e_aceita(cliente, cliente_sem_login, monkeypatch):
    configurar_chave(monkeypatch, "x" * 32)
    criar_lote(cliente)
    assert faixa_da_placa(cliente_sem_login, "x" * 32).status_code == 200


def test_log_avisa_quando_a_chave_falta_ou_e_curta(caplog):
    caplog.set_level(logging.WARNING)
    for chave_ruim in [None, "", "chave-curta-abc"]:
        caplog.clear()
        avisar_se_a_chave_for_invalida(chave_ruim)
        assert "PLANTSYNC_CHAVE_DISPOSITIVO" in caplog.text
        assert "503" in caplog.text


def test_log_nao_avisa_quando_a_chave_esta_certa(caplog):
    caplog.set_level(logging.WARNING)
    avisar_se_a_chave_for_invalida(CHAVE)
    assert caplog.text == ""


# ---------- a chave nunca aparece ----------

def test_chave_nao_aparece_em_log_nem_em_resposta(
    cliente, cliente_sem_login, com_chave_configurada, caplog
):
    caplog.set_level(logging.DEBUG)
    errada = "chave-errada-que-tambem-nao-pode-aparecer"
    criar_lote(cliente)
    respostas = [
        faixa_da_placa(cliente_sem_login),
        faixa_da_placa(cliente_sem_login, errada),
        cliente_sem_login.get(FAIXA),
    ]
    for resposta in respostas:
        assert CHAVE not in resposta.text
        assert errada not in resposta.text
    assert CHAVE not in caplog.text
    assert errada not in caplog.text


def test_aviso_de_chave_curta_nao_mostra_a_chave(caplog):
    caplog.set_level(logging.WARNING)
    avisar_se_a_chave_for_invalida("chave-curta-abc")
    assert "chave-curta-abc" not in caplog.text


def test_painel_no_navegador_nao_pode_enviar_a_chave(cliente_sem_login):
    # O CORS so libera Authorization e Content-Type: a chave e so da placa.
    resposta = cliente_sem_login.options(FAIXA, headers={
        "Origin": "http://localhost:5500",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "x-chave-dispositivo",
    })
    assert resposta.status_code == 400
