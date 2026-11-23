"""Perfil próprio e identidade da empresa respeitam o contexto e sobrevivem ao reinício."""

import pytest

from models.contas import Conta, Empresa, VinculoConta
from services.acessos import preparar_conta_inicial


@pytest.fixture
def acesso_operacional(cliente, banco):
    with banco() as sessao:
        empresa, conta = preparar_conta_inicial(
            sessao, "operador-novo", "senha-apenas-testes-2026", "Empresa de teste",
        )
        sessao.commit()
        ids = empresa.id, conta.id
    resposta = cliente.post("/api/v1/login", json={
        "usuario": "operador-novo", "senha": "senha-apenas-testes-2026",
    })
    assert resposta.status_code == 200
    headers = {"Authorization": "Bearer " + resposta.json()["token"], "X-Empresa-ID": str(ids[0])}
    return cliente, headers, ids


def test_preferencias_persistem_sem_alterar_identidade_de_login(acesso_operacional, banco):
    cliente, headers, (_, conta_id) = acesso_operacional
    resposta = cliente.patch("/api/v1/perfil", headers=headers, json={
        "nome": "Nome de exibição", "fuso": "America/Recife", "avisos_conservacao": False,
    })
    assert resposta.status_code == 200
    perfil = cliente.get("/api/v1/perfil", headers=headers).json()
    assert perfil["nome"] == "Nome de exibição"
    assert perfil["avisos_conservacao"] is False
    with banco() as sessao:
        assert sessao.get(Conta, conta_id).nome == "operador-novo"
    assert cliente.patch("/api/v1/perfil", headers=headers, json={"plataforma": True}).status_code == 400


def test_renomear_empresa_preserva_bootstrap_no_reinicio(acesso_operacional, banco):
    cliente, headers, (empresa_id, conta_id) = acesso_operacional
    resposta = cliente.patch("/api/v1/configuracoes/empresa", headers=headers, json={"nome": "Empresa renomeada"})
    assert resposta.status_code == 200
    with banco() as sessao:
        empresa, conta = preparar_conta_inicial(
            sessao, "operador-novo", "senha-apenas-testes-2026", "Empresa de teste",
        )
        assert empresa.id == empresa_id
        assert empresa.nome == "Empresa renomeada"
        assert conta.id == conta_id
        assert sessao.query(Empresa).count() == 1


def test_cliente_nao_altera_empresa_e_nao_forja_contexto(acesso_operacional, banco):
    cliente, headers, (empresa_id, conta_id) = acesso_operacional
    with banco() as sessao:
        sessao.get(VinculoConta, (conta_id, empresa_id)).papel = "cliente"
        outra = Empresa(nome="Outra empresa")
        sessao.add(outra)
        sessao.commit()
        outra_id = outra.id
    assert cliente.patch("/api/v1/configuracoes/empresa", headers=headers, json={"nome": "Tentativa"}).status_code == 403
    forjados = {**headers, "X-Empresa-ID": str(outra_id)}
    assert cliente.get("/api/v1/configuracoes/empresa", headers=forjados).status_code == 403
