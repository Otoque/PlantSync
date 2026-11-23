"""Registros operacionais v1. Os instantes são armazenados em UTC."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.banco import Base


class Ambiente(Base):
    __tablename__ = "operacao_ambientes"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    nome: Mapped[str]
    tipo: Mapped[str]
    versao: Mapped[int] = mapped_column(default=1)


class FonteSensor(Base):
    __tablename__ = "operacao_fontes"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"), UniqueConstraint("canal"))

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    nome: Mapped[str]
    tipo: Mapped[str]
    canal: Mapped[int | None]
    versao: Mapped[int] = mapped_column(default=1)


class VinculoSensor(Base):
    __tablename__ = "operacao_vinculos_sensor"
    __table_args__ = (
        CheckConstraint("fim IS NULL OR fim >= inicio"),
        Index("ix_operacao_vinculo_ambiente_inicio", "ambiente_id", "inicio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ambiente_id: Mapped[int] = mapped_column(ForeignKey("operacao_ambientes.id"))
    fonte_id: Mapped[int] = mapped_column(ForeignKey("operacao_fontes.id"), index=True)
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]
    instalado_por: Mapped[str | None]
    removido_por: Mapped[str | None]


class FluxoVersao(Base):
    __tablename__ = "operacao_fluxos"

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    versao: Mapped[int] = mapped_column(primary_key=True)
    configuracao: Mapped[dict] = mapped_column(JSON)
    criado_em: Mapped[datetime]
    autor_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))


class Viagem(Base):
    __tablename__ = "operacao_viagens"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    veiculo: Mapped[str]
    transportadora: Mapped[str]
    responsavel: Mapped[str]
    origem: Mapped[str]
    criado_em: Mapped[datetime]
    fonte: Mapped[str | None]
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}


class Parada(Base):
    __tablename__ = "operacao_paradas"
    __table_args__ = (UniqueConstraint("viagem_id", "ordem"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    viagem_id: Mapped[int] = mapped_column(ForeignKey("operacao_viagens.id"))
    ordem: Mapped[int]
    nome: Mapped[str]


class LoteOperacional(Base):
    __tablename__ = "operacao_lotes"
    __table_args__ = (
        CheckConstraint("fase >= 0 AND fase <= 3"),
        CheckConstraint("temp_min_c < temp_max_c"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    legado_id: Mapped[int | None] = mapped_column(unique=True)
    codigo_publico: Mapped[str] = mapped_column(unique=True)
    fruta_id: Mapped[str] = mapped_column(ForeignKey("frutas.id"))
    fruta_nome: Mapped[str]
    variedade: Mapped[str] = mapped_column(default="")
    cliente: Mapped[str] = mapped_column(default="")
    produtor: Mapped[str]
    origem: Mapped[str]
    destino: Mapped[str]
    tipo_destino: Mapped[str] = mapped_column(default="mercado_interno")
    caixas: Mapped[int | None]
    peso_kg: Mapped[float | None]
    temp_min_c: Mapped[float]
    temp_max_c: Mapped[float]
    umidade_min_pct: Mapped[float]
    umidade_max_pct: Mapped[float]
    fase: Mapped[int] = mapped_column(default=0)
    versao: Mapped[int] = mapped_column(default=1)
    preparado_em: Mapped[datetime]
    carregado_em: Mapped[datetime | None]
    despachado_em: Mapped[datetime | None]
    recebido_em: Mapped[datetime | None]
    responsavel_empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    responsavel_nome: Mapped[str]
    fluxo_versao: Mapped[int] = mapped_column(default=0)
    ambiente_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_ambientes.id"))
    viagem_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_viagens.id"), index=True)
    parada_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_paradas.id"))
    pendente: Mapped[bool] = mapped_column(default=False)
    transferencia_pendente_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"))
    __mapper_args__ = {"version_id_col": versao}


class Permanencia(Base):
    __tablename__ = "operacao_permanencias"
    __table_args__ = (
        CheckConstraint("fim IS NULL OR fim >= inicio"),
        Index("ix_operacao_permanencia_lote_inicio", "lote_id", "inicio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"))
    ambiente_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_ambientes.id"))
    fase: Mapped[int]
    responsavel_empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    responsavel_nome: Mapped[str]
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]
    viagem_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_viagens.id"))


class LeituraFonte(Base):
    __tablename__ = "operacao_leituras"
    __table_args__ = (Index("ix_operacao_leitura_fonte_hora", "fonte_id", "data_hora"),)

    fonte_id: Mapped[int] = mapped_column(ForeignKey("operacao_fontes.id"), primary_key=True)
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    data_hora: Mapped[datetime]
    recebida_em: Mapped[datetime]
    temperatura_c: Mapped[float]
    umidade_pct: Mapped[float | None]
    luminosidade_lux: Mapped[float | None]


class EventoLote(Base):
    __tablename__ = "operacao_eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"), index=True)
    tipo: Mapped[str]
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"))
    integracao_id: Mapped[int | None]
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    autor_nome: Mapped[str]
    empresa_nome: Mapped[str]
    efetivo_em: Mapped[datetime]
    registrado_em: Mapped[datetime]
    fase_anterior: Mapped[int | None]
    fase_atual: Mapped[int]
    motivo: Mapped[str | None]
    dados: Mapped[dict] = mapped_column(JSON, default=dict)


class CompartilhamentoLote(Base):
    __tablename__ = "operacao_compartilhamentos"
    __table_args__ = (UniqueConstraint("lote_id", "empresa_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"), index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    direitos: Mapped[list] = mapped_column(JSON)
    criado_em: Mapped[datetime]
    expira_em: Mapped[datetime]
    aceito_em: Mapped[datetime | None]
    revogado_em: Mapped[datetime | None]
    inicio_dados: Mapped[datetime | None]
    fim_dados: Mapped[datetime | None]
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}


class FontePosicao(Base):
    __tablename__ = "operacao_fontes_posicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    viagem_id: Mapped[int] = mapped_column(ForeignKey("operacao_viagens.id"), index=True)
    fonte: Mapped[str]
    ator: Mapped[str]
    autor_nome: Mapped[str]
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]
    motivo_fim: Mapped[str | None]


class PosicaoViagem(Base):
    __tablename__ = "operacao_posicoes"
    __table_args__ = (UniqueConstraint("viagem_id", "fonte_id", "entrada"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    viagem_id: Mapped[int] = mapped_column(ForeignKey("operacao_viagens.id"), index=True)
    fonte_id: Mapped[int] = mapped_column(ForeignKey("operacao_fontes_posicao.id"))
    fonte: Mapped[str]
    entrada: Mapped[str]
    latitude: Mapped[float]
    longitude: Mapped[float]
    precisao: Mapped[float | None]
    medida_em: Mapped[datetime]
    recebida_em: Mapped[datetime]


class ComandoOperacional(Base):
    __tablename__ = "operacao_comandos"

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), primary_key=True)
    ator: Mapped[str] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(primary_key=True)
    assinatura: Mapped[str]
    resultado: Mapped[dict] = mapped_column(JSON)
    registrado_em: Mapped[datetime]


class Ocorrencia(Base):
    __tablename__ = "operacao_ocorrencias"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"), index=True)
    deduplicacao: Mapped[str] = mapped_column(unique=True)
    tipo: Mapped[str]
    fonte_id: Mapped[int | None] = mapped_column(ForeignKey("operacao_fontes.id"))
    responsavel_empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    inicio: Mapped[datetime]
    fim: Mapped[datetime | None]
    estado: Mapped[str] = mapped_column(default="aberta")
    detalhe: Mapped[str]
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}


class LaudoOperacional(Base):
    __tablename__ = "operacao_laudos"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    criado_em: Mapped[datetime]
    expira_em: Mapped[datetime | None]
    revogado_em: Mapped[datetime | None]


class RevisaoLaudo(Base):
    __tablename__ = "operacao_revisoes_laudo"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("operacao_lotes.id"), index=True)
    laudo_id: Mapped[int] = mapped_column(ForeignKey("operacao_laudos.id"), unique=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    emitido_em: Mapped[datetime]
    motivo: Mapped[str]
    documento: Mapped[dict] = mapped_column(JSON)
