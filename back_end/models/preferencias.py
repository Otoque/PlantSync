"""Preferências pessoais, sem alterar a identidade usada no login."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class PreferenciaConta(Base):
    __tablename__ = "preferencias_conta"

    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), primary_key=True)
    nome: Mapped[str]
    fuso: Mapped[str] = mapped_column(default="America/Sao_Paulo")
    idioma: Mapped[str] = mapped_column(default="pt-BR")
    avisos_conservacao: Mapped[bool] = mapped_column(default=True)
