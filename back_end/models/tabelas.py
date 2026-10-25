"""
Tabelas do banco.

Datas sao gravadas em UTC e sem fuso (o SQLite nao guarda fuso).
A conversao para o horario de Recife fica com o painel.

Cada linha "nome: Mapped[tipo]" cria uma coluna daquele tipo.
"Mapped[tipo | None]" quer dizer que a coluna aceita ficar vazia.
"""

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class Fruta(Base):
    __tablename__ = "frutas"

    id: Mapped[str] = mapped_column(primary_key=True)
    nome: Mapped[str]
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]
    fonte: Mapped[str]


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruta_id: Mapped[str] = mapped_column(ForeignKey("frutas.id"))
    origem: Mapped[str]
    porto_destino: Mapped[str]
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]

    # Copia da faixa segura no momento em que o lote foi criado.
    # Assim, editar a fruta depois nao muda a analise de lotes antigos.
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]


class Leitura(Base):
    __tablename__ = "leituras"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Numero da entrada no ThingSpeak; evita gravar a mesma leitura duas vezes.
    entry_id: Mapped[int] = mapped_column(unique=True)
    data_hora: Mapped[datetime] = mapped_column(index=True)
    temperatura_c: Mapped[float]
    umidade_pct: Mapped[float | None]
    luminosidade_lux: Mapped[float | None]
