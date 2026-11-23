"""Faixas de uma empresa não alteram o catálogo ou os lotes de outra."""

from datetime import timedelta

import pytest

from models.contas import Conta, Empresa, SessaoConta, VinculoConta
from models.tabelas import Fruta
from services.autenticacao import hash_do_token
from services.datas import agora_utc


@pytest.fixture
def catalogos(cliente, banco):
    with banco() as sessao:
        for numero in (1, 2):
            conta = Conta(id=numero, nome=f"catálogo-{numero}", sal="00" * 16, senha_hash="não usado")
            empresa = Empresa(id=numero, nome=f"Empresa catálogo {numero}")
            sessao.add_all([conta, empresa])
            sessao.flush()
            sessao.add(VinculoConta(conta_id=numero, empresa_id=numero, papel="administrador"))
            sessao.add(SessaoConta(
                token_hash=hash_do_token(f"pss_catalogo{numero}"), conta_id=numero,
                expira_em=agora_utc() + timedelta(hours=1),
            ))
        sessao.commit()
    return cliente


def headers(numero):
    return {"Authorization": f"Bearer pss_catalogo{numero}", "X-Empresa-ID": str(numero)}


def test_especializar_faixa_nao_altera_outra_empresa_ou_lote(catalogos, banco):
    cliente = catalogos
    antes = cliente.get("/api/v1/frutas", headers=headers(1)).json()
    uva = next(fruta for fruta in antes if fruta["id"] == "uva")
    alterada = cliente.patch("/api/v1/frutas/uva", headers=headers(1), json={
        "version": uva["version"], "temp_max_c": 3,
    })
    assert alterada.status_code == 200
    outra = cliente.get("/api/v1/frutas", headers=headers(2)).json()
    assert next(fruta for fruta in outra if fruta["id"] == "uva")["temp_max_c"] == 2
    with banco() as sessao:
        assert sessao.get(Fruta, "uva").temp_max_c == 2
    ambiente = cliente.post("/api/v1/ambientes", headers=headers(1), json={"name": "Câmara", "type": "camara"})
    assert ambiente.status_code == 201
    lote = cliente.post("/api/v1/lotes", headers=headers(1), json={
        "fruitId": "uva", "client": "Cliente", "destination": "Recife", "environmentId": ambiente.json()["id"],
    })
    assert lote.status_code == 201
    assert lote.json()["range"] == [0, 3]
    segunda = cliente.patch("/api/v1/frutas/uva", headers=headers(1), json={
        "version": alterada.json()["version"], "temp_max_c": 4,
    })
    assert segunda.status_code == 200
    assert cliente.get("/api/v1/lotes/" + lote.json()["id"], headers=headers(1)).json()["range"] == [0, 3]


def test_fruta_propria_nao_fica_disponivel_em_outra_empresa(catalogos):
    cliente = catalogos
    resposta = cliente.post("/api/v1/frutas", headers=headers(1), json={
        "nome": "Melão", "temp_min_c": 5, "temp_max_c": 10,
        "umidade_min_pct": 85, "umidade_max_pct": 95, "fonte": "Referência de teste",
    })
    assert resposta.status_code == 201
    fruta_id = resposta.json()["id"]
    assert fruta_id not in [fruta["id"] for fruta in cliente.get("/api/v1/frutas", headers=headers(2)).json()]
    assert cliente.patch("/api/v1/frutas/" + fruta_id, headers=headers(2), json={
        "version": 1, "nome": "Outro nome",
    }).status_code == 404
    ambiente = cliente.post("/api/v1/ambientes", headers=headers(2), json={"name": "Outra câmara", "type": "camara"}).json()
    tentativa = cliente.post("/api/v1/lotes", headers=headers(2), json={
        "fruitId": fruta_id, "client": "Cliente", "destination": "Recife", "environmentId": ambiente["id"],
    })
    assert tentativa.status_code == 404


def test_catalogo_recusa_faixa_invertida_e_versao_antiga(catalogos):
    cliente = catalogos
    invertida = cliente.patch("/api/v1/frutas/uva", headers=headers(1), json={
        "version": 0, "temp_min_c": 5, "temp_max_c": 2,
    })
    assert invertida.status_code == 400
    primeira = cliente.patch("/api/v1/frutas/uva", headers=headers(1), json={"version": 0, "temp_max_c": 3})
    assert primeira.status_code == 200
    repetida = cliente.patch("/api/v1/frutas/uva", headers=headers(1), json={"version": 0, "temp_max_c": 4})
    assert repetida.status_code == 409
