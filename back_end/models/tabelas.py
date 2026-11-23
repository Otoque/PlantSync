"""
Tabelas do banco.

Datas sao gravadas em UTC e sem fuso (o SQLite nao guarda fuso).
A conversao para o horario de Recife fica com o painel.

Cada linha "nome: Mapped[tipo]" cria uma coluna daquele tipo.
"Mapped[tipo | None]" quer dizer que a coluna aceita ficar vazia.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.banco import Base


class Fruta(Base):
    __tablename__ = "frutas"

    id: Mapped[str] = mapped_column(primary_key=True)
    nome: Mapped[str]
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]
    # Nome do dano que o frio causa na fruta (ex.: "corte negro"). Pode ficar vazio.
    risco_no_frio: Mapped[str | None]
    fonte: Mapped[str]


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruta_id: Mapped[str] = mapped_column(ForeignKey("frutas.id"))
    produtor: Mapped[str]
    origem: Mapped[str]
    # Para onde o caminhao leva a carga: um porto (exportacao) ou o mercado
    # interno (Ceasa, atacado). Ex.: destino "Ceasa Recife", tipo "mercado_interno".
    destino: Mapped[str]
    tipo_destino: Mapped[str]
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]

    # Codigos aleatorios do laudo (ver services/laudos.py):
    # o publico vai no QR Code; o token e o segredo do laudo completo.
    codigo_publico: Mapped[str] = mapped_column(unique=True)
    token_laudo: Mapped[str] = mapped_column(unique=True)

    # Copia da faixa segura no momento em que o lote foi criado.
    # Assim, editar a fruta depois nao muda a analise de lotes antigos.
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]
    vinculo: Mapped["VinculoDispositivo | None"] = relationship(cascade="all, delete-orphan")


class Leitura(Base):
    __tablename__ = "leituras"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Numero da entrada no ThingSpeak; evita gravar a mesma leitura duas vezes.
    entry_id: Mapped[int] = mapped_column(unique=True)
    data_hora: Mapped[datetime] = mapped_column(index=True)
    temperatura_c: Mapped[float]
    umidade_pct: Mapped[float | None]
    luminosidade_lux: Mapped[float | None]


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    canal: Mapped[int] = mapped_column(unique=True)


class VinculoDispositivo(Base):
    __tablename__ = "vinculos_dispositivo"

    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), primary_key=True)
    dispositivo_id: Mapped[int | None] = mapped_column(ForeignKey("dispositivos.id"), index=True)
    # A unicidade impede dois lotes de ocuparem a mesma placa simultaneamente.
    # Zero reserva o canal padrão. Ao encerrar a viagem, liberamos a ocupação.
    ocupacao: Mapped[int | None] = mapped_column(unique=True)
    dispositivo: Mapped[Dispositivo] = relationship()


class LeituraDispositivo(Base):
    __tablename__ = "leituras_dispositivo"
    __table_args__ = (Index("ix_leitura_dispositivo_hora", "dispositivo_id", "data_hora"),)

    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"), primary_key=True)
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    data_hora: Mapped[datetime]
    temperatura_c: Mapped[float]
    umidade_pct: Mapped[float | None]
    luminosidade_lux: Mapped[float | None]


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(unique=True)
    # A senha nunca e gravada: so o sal e o hash dela (ver services/autenticacao.py).
    sal: Mapped[str]
    senha_hash: Mapped[str]


class TokenDeAcesso(Base):
    __tablename__ = "tokens_de_acesso"

    # Guarda o hash do token, nao o token: quem ler o banco nao consegue entrar.
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    expira_em: Mapped[datetime]
