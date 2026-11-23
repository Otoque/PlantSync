"""Controle das conversões do banco legado para a operação por empresa."""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class RegistroMigracao(Base):
    __tablename__ = "registros_migracao"

    chave: Mapped[str] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    aplicado_em: Mapped[datetime]
    resumo: Mapped[dict] = mapped_column(JSON)
