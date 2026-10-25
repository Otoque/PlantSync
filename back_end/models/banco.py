"""Conexao com o banco de dados (SQLAlchemy)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DATABASE_URL

# O SQLite, por padrao, so deixa a thread que abriu a conexao usa-la.
# O FastAPI atende requisicoes em threads diferentes, entao liberamos.
opcoes_conexao = {}
if DATABASE_URL.startswith("sqlite"):
    opcoes_conexao = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=opcoes_conexao)
SessaoLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def abrir_sessao():
    """Entrega uma sessao do banco para a rota e fecha ao terminar."""
    sessao = SessaoLocal()
    try:
        yield sessao
    finally:
        sessao.close()
