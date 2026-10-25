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
from services.frutas import cadastrar_frutas_iniciais


@pytest.fixture
def cliente():
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

    def abrir_sessao_teste():
        sessao = SessaoTeste()
        try:
            yield sessao
        finally:
            sessao.close()

    app.dependency_overrides[abrir_sessao] = abrir_sessao_teste
    yield TestClient(app)
    app.dependency_overrides.clear()
