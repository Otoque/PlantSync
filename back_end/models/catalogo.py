"""Faixas e nomes do catálogo de conservação de cada empresa."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class CatalogoFruta(Base):
    __tablename__ = "catalogo_frutas"

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    fruta_id: Mapped[str] = mapped_column(ForeignKey("frutas.id"), primary_key=True)
    nome: Mapped[str]
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]
    risco_no_frio: Mapped[str | None]
    fonte: Mapped[str]
    ativo: Mapped[bool] = mapped_column(default=True)
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}

    @property
    def id(self):
        return self.fruta_id
