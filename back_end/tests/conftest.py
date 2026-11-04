"""
Prepara um banco SQLite em memoria para cada teste, assim os testes
nunca mexem no plantsync.db de verdade.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app
from models.banco import Base, abrir_sessao
from models.tabelas import Usuario
from services.autenticacao import abrir_sessao_de_login
from services.frutas import cadastrar_frutas_iniciais


def token_de_teste(banco):
    """
    Abre uma sessao direto no banco, sem passar pelo POST /api/login: o hash da
    senha e lento de proposito e deixaria cada um dos testes bem mais demorado.
    """
    with banco() as sessao:
        usuario = Usuario(nome="teste", sal="nao usado", senha_hash="nao usado")
        sessao.add(usuario)
        sessao.commit()
        return abrir_sessao_de_login(sessao, usuario)["token"]


@pytest.fixture
def banco():
    """Cria o banco de teste (com uva e manga) e devolve a fabrica de sessoes dele."""
    # StaticPool mantem uma unica conexao, senao cada conexao veria
    # um banco em memoria diferente (e vazio).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessaoTeste = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with SessaoTeste() as sessao:
        cadastrar_frutas_iniciais(sessao)
    return SessaoTeste


@pytest.fixture
def cliente(banco):
    """Cliente HTTP da API ligado ao banco de teste, ja com login feito."""

    # O FastAPI chama esta funcao a cada requisicao para obter uma sessao;
    # ela entrega a sessao no yield e a fecha quando a requisicao termina.
    def abrir_sessao_teste():
        sessao = banco()
        try:
            yield sessao
        finally:
            sessao.close()

    # Troca o banco de verdade pelo de teste em todas as rotas.
    app.dependency_overrides[abrir_sessao] = abrir_sessao_teste
    # O teste roda neste yield; depois, as rotas voltam ao banco normal.
    yield TestClient(app, headers={"Authorization": f"Bearer {token_de_teste(banco)}"})
    app.dependency_overrides.clear()


@pytest.fixture
def cliente_sem_login(cliente):
    """Cliente HTTP ligado ao mesmo banco de teste, mas sem token de login."""
    return TestClient(app)
