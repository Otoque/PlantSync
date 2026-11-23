"""Identidades, vínculos e credenciais da API por empresa."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, text
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(unique=True)
    ativo: Mapped[bool] = mapped_column(default=True)


class Conta(Base):
    __tablename__ = "contas"
    __table_args__ = (
        Index("ix_conta_nome_sem_email", "nome", unique=True,
              sqlite_where=text("email IS NULL"), postgresql_where=text("email IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    email: Mapped[str | None] = mapped_column(unique=True)
    sal: Mapped[str]
    senha_hash: Mapped[str]
    ativo: Mapped[bool] = mapped_column(default=True)
    plataforma: Mapped[bool] = mapped_column(default=False)


class ContaInicial(Base):
    __tablename__ = "conta_inicial"

    chave: Mapped[str] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))


class VinculoConta(Base):
    __tablename__ = "vinculos_conta"
    __table_args__ = (
        CheckConstraint("papel IN ('administrador', 'gestor', 'cliente')", name="ck_vinculo_papel"),
    )

    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True, index=True)
    papel: Mapped[str]
    ativo: Mapped[bool] = mapped_column(default=True)


class PermissoesPapel(Base):
    __tablename__ = "permissoes_papel"

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    papel: Mapped[str] = mapped_column(primary_key=True)
    permissoes: Mapped[list[str]] = mapped_column(JSON)


class SessaoConta(Base):
    __tablename__ = "sessoes_conta"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    expira_em: Mapped[datetime] = mapped_column(index=True)


class ConviteConta(Base):
    __tablename__ = "convites_conta"
    __table_args__ = (Index("ix_convite_empresa_email", "empresa_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    email: Mapped[str]
    papel: Mapped[str]
    primeiro_administrador: Mapped[bool] = mapped_column(default=False)
    expira_em: Mapped[datetime]
    usado_em: Mapped[datetime | None]
    revogado_em: Mapped[datetime | None]


class EventoAcesso(Base):
    __tablename__ = "eventos_acesso"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    acao: Mapped[str]
    dados: Mapped[dict] = mapped_column(JSON)
    registrado_em: Mapped[datetime]


class TentativaLogin(Base):
    __tablename__ = "tentativas_login"

    chave: Mapped[str] = mapped_column(primary_key=True)
    janela: Mapped[int] = mapped_column(primary_key=True, index=True)
    quantidade: Mapped[int]


class Integracao(Base):
    __tablename__ = "integracoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    nome: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)
    permissoes: Mapped[list[str]] = mapped_column(JSON)
    recurso_tipo: Mapped[str | None]
    recurso_id: Mapped[str | None]
    expira_em: Mapped[datetime]
    revogado_em: Mapped[datetime | None]
    ultimo_uso_em: Mapped[datetime | None]
