"""Rotas v1 de lotes, ambientes, viagens, conservação, laudos e fluxo."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.limites import TEMP_FISICA_MAX, TEMP_FISICA_MIN
from models.operacao import Ambiente, FonteSensor, LoteOperacional, Ocorrencia
from security.audit_log import log_security_block
from services import operacao as fluxo, operacao_monitoramento as monitor, operacao_viagens as viagens
from services.acessos import Contexto, exigir, obter_contexto
from services.datas import agora_utc
from services.operacao_acesso import (
    conferir_versao, dono, efetivo, erro, escopo, executar,
    exigir_escopo, instante, lote_acessivel, lotes_visiveis, registrar_evento, transacao,
)


router = APIRouter(prefix="/api/v1", tags=["operação"])
Banco = Annotated[Session, Depends(abrir_sessao)]
Ctx = Annotated[Contexto, Depends(obter_contexto)]
Chave = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]
Deslocamento = Annotated[int, Query(ge=0)]
Pagina = Annotated[int, Query(ge=1, le=1000)]
Nome = Annotated[str, Field(min_length=1, max_length=160)]
Texto = Annotated[str, Field(max_length=240)]
Motivo = Annotated[str, Field(min_length=1, max_length=1000)]
Positivo = Annotated[int, Field(gt=0)]
Versao = Annotated[int, Field(ge=0)]
CodigoLote = Annotated[str, Field(pattern=r"^PS-[A-Z0-9][A-Z0-9-]{0,31}$")]
CodigoViagem = Annotated[str, Field(pattern=r"^V-[A-Z0-9][A-Z0-9-]{0,31}$")]
Temperatura = Annotated[float, Field(ge=TEMP_FISICA_MIN, le=TEMP_FISICA_MAX)]
Peso = Annotated[float, Field(gt=0, le=1_000_000)]
FonteGPS = Literal["celular", "externa"]
TipoDestino = Literal["mercado_interno", "exportacao"]
AcaoFluxo = Literal["editar", "preparar", "carregar", "despachar", "receber", "retornar", "validar-despacho", "confirmar-transferencia"]
PapelFluxo = Literal["administrador", "gestor", "cliente", "integracao", "automacao"]


class Dados(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False, populate_by_name=True)


class EmVersao(Dados):
    version: Versao | None = None


class Faixa(Dados):
    range: tuple[Temperatura, Temperatura] | None = None

    @model_validator(mode="after")
    def validar_faixa(self):
        if self.range is not None and self.range[0] >= self.range[1]:
            raise ValueError("A temperatura mínima deve ser menor que a máxima.")
        return self


class CriarLote(Faixa):
    id: CodigoLote | None = None
    fruitId: Nome
    variety: Texto = ""
    client: Nome
    destination: Nome
    destinationType: TipoDestino = "mercado_interno"
    boxes: Positivo | None = None
    weightKg: Peso | None = None
    environmentId: Positivo
    preparedAt: datetime | None = None
    origin: Texto = ""
    producer: Nome | None = None
    reason: Motivo | None = None


class EditarLote(Faixa, EmVersao):
    variety: Texto | None = None
    client: Nome | None = None
    destination: Nome | None = None
    destinationType: TipoDestino | None = None
    boxes: Positivo | None = None
    weightKg: Peso | None = None
    origin: Texto | None = None
    producer: Nome | None = None
    reason: Motivo | None = None


class Movimento(EmVersao):
    effectiveAt: datetime | None = None
    environmentId: Positivo | None = None
    tripId: CodigoViagem | None = None
    stopId: Positivo | None = None
    responsibleCompanyId: Positivo | None = None
    reason: Motivo | None = None


class CriarAmbiente(Dados):
    name: Nome
    type: Literal["camara", "compartimento"]


class CriarSensor(Dados):
    name: Nome
    type: Literal["thingspeak", "manual"] = "thingspeak"
    channel: Positivo | None = None
    environmentId: Positivo | None = None
    effectiveAt: datetime | None = None

    @model_validator(mode="after")
    def validar_canal(self):
        if (self.type == "thingspeak") != (self.channel is not None):
            raise ValueError("Informe um canal somente para fontes ThingSpeak.")
        return self


class VincularSensor(Dados):
    environmentId: Positivo
    effectiveAt: datetime | None = None


class EncerrarVinculo(Dados):
    effectiveAt: datetime | None = None


class LeituraManual(Dados):
    entryId: Positivo
    measuredAt: datetime
    temperature: Temperatura
    humidity: Annotated[float, Field(ge=0, le=100)] | None = None
    lux: Annotated[float, Field(ge=0, le=200000)] | None = None


class CriarParada(Dados):
    name: Nome


class CriarViagem(Dados):
    id: CodigoViagem | None = None
    vehicle: Nome
    carrier: Nome
    responsible: Nome
    origin: Texto = ""
    source: FonteGPS | None = None
    stops: list[CriarParada] = Field(default_factory=list, max_length=100)
    createdAt: datetime | None = None


class IniciarRastreio(EmVersao):
    source: FonteGPS


class EncerrarRastreio(EmVersao):
    reason: Motivo | None = None


class Posicao(Dados):
    entryId: Nome
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    accuracy: Annotated[float, Field(ge=0, le=100000)] | None = None
    measuredAt: datetime
    source: FonteGPS


class Compartilhar(Dados):
    companyId: Positivo
    rights: list[Literal["consultar", "laudo", "receber", "rota", "operar"]] = Field(min_length=1, max_length=5)
    expiresAt: datetime | None = None
    dataFrom: datetime | None = Field(None, alias="from")
    dataTo: datetime | None = Field(None, alias="to")


class EmitirLaudo(Dados):
    expiresAt: datetime | None = None
    reason: Motivo | None = None


class Deteccao(Dados):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    radiusMeters: Annotated[float, Field(ge=10, le=10_000)]
    maxAccuracyMeters: Annotated[float, Field(gt=0, le=1000)]
    maxAgeMinutes: Annotated[int, Field(ge=1, le=120)]
    persistenceSeconds: Annotated[int, Field(ge=1, le=3600)]
    autoDelaySeconds: Annotated[int, Field(ge=1, le=3600)]


class ConfigurarFluxo(EmVersao):
    transferAt: Literal["carregamento", "despacho", "recebimento"] | None = None
    requireAcceptance: bool | None = None
    automatic: bool | None = None
    absenceMinutes: Annotated[int, Field(ge=1, le=2880)] | None = None
    departureDetection: Deteccao | None = None
    allowedRolesByAction: dict[AcaoFluxo, list[PapelFluxo]] | None = None


class Sincronizar(Dados):
    sensorId: Positivo | None = None
    fromDate: datetime | None = Field(None, alias="from")


class TratarOcorrencia(EmVersao):
    status: Literal["reconhecida", "resolvida"]
    reason: Motivo


def dados_editaveis(dados, nulos=()):
    return {campo: valor for campo, valor in dados.model_dump(exclude_unset=True, by_alias=True).items()
            if valor is not None or campo in nulos}


def mutacao(sessao, ctx, chave, acao, dados, funcao, comp=None):
    with transacao(sessao):
        return executar(sessao, ctx, chave, acao, dados.model_dump(mode="json", by_alias=True), funcao, comp)


def dados_lote_mutado(sessao, ctx, lote, comp=None):
    sessao.flush()
    if "consultar" not in ctx.permissoes:
        return {"id": lote.codigo, "phase": lote.fase, "version": lote.versao}
    return monitor.dados_lote(sessao, ctx, lote, comp)


def exigir_humano(ctx):
    if ctx.integracao:
        erro(403, "A ação exige uma conta individual.")


@router.get("/lotes")
def listar_lotes(sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100,
                 busca: Annotated[str | None, Query(max_length=240)] = None,
                 fase: Annotated[int | None, Query(ge=0, le=3)] = None):
    exigir(ctx, "consultar")
    lotes = lotes_visiveis(sessao, ctx, offset=offset, limit=limit, busca=busca, fase=fase)
    return [monitor.dados_lote(sessao, ctx, lote) for lote in lotes]


@router.post("/lotes", status_code=201)
def criar_lote(dados: CriarLote, sessao: Banco, ctx: Ctx, chave: Chave = None):
    exigir(ctx, "operar")
    return mutacao(sessao, ctx, chave, "criar_lote", dados,
                   lambda: dados_lote_mutado(sessao, ctx, fluxo.novo_lote(sessao, ctx, dados_editaveis(dados))))


@router.get("/lotes/{codigo}")
def detalhe_lote(codigo: str, sessao: Banco, ctx: Ctx):
    lote, comp = lote_acessivel(sessao, ctx, codigo)
    return monitor.dados_lote(sessao, ctx, lote, comp, detalhe=True)


@router.patch("/lotes/{codigo}")
def editar_lote(codigo: str, dados: EditarLote, sessao: Banco, ctx: Ctx, chave: Chave = None):
    lote, comp = lote_acessivel(sessao, ctx, codigo, "operar")
    dono(ctx, lote)
    return mutacao(sessao, ctx, chave, f"editar:{lote.id}", dados, lambda: dados_lote_mutado(
        sessao, ctx, fluxo.editar_lote(sessao, ctx, lote, dados_editaveis(dados, {"boxes", "weightKg"})), comp,
    ))


def comando_lote(codigo, acao, dados, sessao, ctx, chave):
    lote, comp = lote_acessivel(sessao, ctx, codigo, "receber" if acao == "receber" else "operar")
    if acao in {"preparar", "carregar", "retornar"}:
        dono(ctx, lote)
    valores = dados_editaveis(dados)

    def aplicar():
        if acao in fluxo.TRANSICOES:
            fluxo.mover(sessao, ctx, lote, acao, valores)
        else:
            funcoes = {"preparar": fluxo.preparar, "retornar": fluxo.retornar,
                       "validar-despacho": fluxo.validar_despacho}
            funcoes[acao](sessao, ctx, lote, valores)
        return dados_lote_mutado(sessao, ctx, lote, comp)

    return mutacao(sessao, ctx, chave, f"{acao}:{lote.id}", dados, aplicar, comp)


@router.post("/lotes/{codigo}/preparar")
def preparar(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "preparar", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/carregar")
def carregar(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "carregar", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/despachar")
def despachar(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "despachar", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/receber")
def receber(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "receber", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/retornar")
def retornar(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "retornar", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/validar-despacho")
def validar_despacho(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    return comando_lote(codigo, "validar-despacho", dados, sessao, ctx, chave)


@router.post("/lotes/{codigo}/confirmar-transferencia")
def confirmar_transferencia(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    lote, comp = lote_acessivel(sessao, ctx, codigo)
    direitos = set(comp.direitos) if comp else {"operar", "receber"}
    globais = set(ctx.permissoes) | ({"receber"} if ctx.papel == "cliente" else set())
    if not direitos & globais & {"operar", "receber"}:
        erro(403, "A confirmação cabe à empresa indicada para assumir a carga.")

    def aplicar():
        fluxo.confirmar_transferencia(sessao, ctx, lote, dados_editaveis(dados))
        return dados_lote_mutado(sessao, ctx, lote, comp)

    return mutacao(sessao, ctx, chave, f"confirmar-transferencia:{lote.id}", dados, aplicar, comp)


@router.get("/lotes/{codigo}/leituras")
def leituras(codigo: str, sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 500,
             de: Annotated[datetime | None, Query(alias="from")] = None,
             ate: Annotated[datetime | None, Query(alias="to")] = None,
             fase: Annotated[int | None, Query(ge=0, le=3)] = None):
    lote, comp = lote_acessivel(sessao, ctx, codigo)
    return monitor.leituras_lote(sessao, lote, comp, instante(de) if de else None,
                                instante(ate) if ate else None, fase, offset, limit)


@router.get("/lotes/{codigo}/historico")
def historico(codigo: str, sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    lote, comp = lote_acessivel(sessao, ctx, codigo)
    return fluxo.eventos_lote(sessao, lote, comp, offset, limit)


@router.get("/ambientes")
def ambientes(sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    exigir(ctx, "operar")
    exigir_escopo(ctx, "ambiente")
    consulta = select(Ambiente).where(Ambiente.empresa_id == ctx.empresa.id).order_by(Ambiente.nome)
    return [monitor.dados_ambiente(sessao, a, ctx) for a in sessao.scalars(consulta.offset(offset).limit(limit))]


@router.post("/ambientes", status_code=201)
def criar_ambiente(dados: CriarAmbiente, sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "operar")
    with transacao(sessao):
        ambiente = Ambiente(nome=dados.name, tipo=dados.type, empresa_id=ctx.empresa.id)
        sessao.add(ambiente)
        sessao.flush()
        return monitor.dados_ambiente(sessao, ambiente, ctx)


@router.get("/sensores")
def sensores(sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    exigir(ctx, "operar" if "operar" in ctx.permissoes else "integrar")
    consulta = select(FonteSensor).where(FonteSensor.empresa_id == ctx.empresa.id).order_by(FonteSensor.nome)
    fontes = [fonte for fonte in sessao.scalars(consulta) if escopo(ctx, "sensor", fonte.id)]
    return [monitor.dados_sensor(sessao, fonte) for fonte in fontes[offset:offset + limit]]


@router.post("/sensores", status_code=201)
def criar_sensor(dados: CriarSensor, sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "operar")
    with transacao(sessao):
        fonte = FonteSensor(empresa_id=ctx.empresa.id, nome=dados.name, tipo=dados.type, canal=dados.channel)
        sessao.add(fonte)
        sessao.flush()
        if dados.environmentId:
            ambiente = fluxo.ambiente_da_empresa(sessao, ctx, dados.environmentId)
            monitor.vincular_sensor(sessao, ctx, fonte, ambiente, efetivo(dados.effectiveAt))
        return monitor.dados_sensor(sessao, fonte)


@router.post("/sensores/{sensor_id}/vincular")
def vincular_sensor(sensor_id: int, dados: VincularSensor, sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "operar")
    fonte = monitor.sensor_da_empresa(sessao, ctx, sensor_id)
    ambiente = fluxo.ambiente_da_empresa(sessao, ctx, dados.environmentId)
    with transacao(sessao):
        monitor.vincular_sensor(sessao, ctx, fonte, ambiente, efetivo(dados.effectiveAt))
        return monitor.dados_sensor(sessao, fonte)


@router.post("/sensores/{sensor_id}/desvincular")
def desvincular_sensor(sensor_id: int, dados: EncerrarVinculo, sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "operar")
    fonte = monitor.sensor_da_empresa(sessao, ctx, sensor_id)
    with transacao(sessao):
        monitor.vincular_sensor(sessao, ctx, fonte, None, efetivo(dados.effectiveAt))
        return monitor.dados_sensor(sessao, fonte)


@router.post("/sensores/{sensor_id}/leituras")
def registro_sensor(sensor_id: int, dados: LeituraManual, sessao: Banco, ctx: Ctx, chave: Chave = None):
    exigir(ctx, "integrar")
    fonte = monitor.sensor_da_empresa(sessao, ctx, sensor_id)
    if fonte.tipo != "manual":
        erro(422, "Esta fonte é alimentada pelo ThingSpeak.")

    def aplicar():
        monitor.reservar(sessao, FonteSensor, [fonte.id])
        estado = monitor.ingerir_leitura(sessao, fonte, {
            "entry_id": dados.entryId, "data_hora": efetivo(dados.measuredAt), "temperatura_c": dados.temperature,
            "umidade_pct": dados.humidity, "luminosidade_lux": dados.lux,
        }, agora_utc() + monitor.FOLGA_DO_RELOGIO)
        monitor.gerar_ocorrencias(sessao, ctx.empresa.id)
        return {"status": estado, "sensorId": fonte.id, "entryId": dados.entryId}

    return mutacao(sessao, ctx, chave, f"registrar-leitura:{sensor_id}", dados, aplicar)


@router.get("/viagens")
def lista_viagens(sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    return viagens.listar_viagens(sessao, ctx, offset, limit)


@router.post("/viagens", status_code=201)
def criar_viagem(dados: CriarViagem, sessao: Banco, ctx: Ctx, chave: Chave = None):
    exigir_humano(ctx)
    exigir(ctx, "operar")

    def aplicar():
        viagem = viagens.nova_viagem(sessao, ctx, dados_editaveis(dados))
        return viagens.dados_viagem(sessao, ctx, viagem)

    return mutacao(sessao, ctx, chave, "criar-viagem", dados, aplicar)


@router.get("/viagens/{codigo}")
def detalhe_viagem(codigo: str, sessao: Banco, ctx: Ctx):
    return viagens.dados_viagem(sessao, ctx, viagens.viagem_acessivel(sessao, ctx, codigo))


@router.post("/viagens/{codigo}/despachar")
def despacho_viagem(codigo: str, dados: Movimento, sessao: Banco, ctx: Ctx, chave: Chave = None):
    viagem = viagens.viagem_acessivel(sessao, ctx, codigo, "operar", escrita=True)
    return mutacao(sessao, ctx, chave, f"despachar-viagem:{viagem.id}", dados,
                   lambda: viagens.despachar_viagem(sessao, ctx, viagem, dados_editaveis(dados)))


@router.post("/viagens/{codigo}/rastreio/iniciar")
def iniciar_rastreio(codigo: str, dados: IniciarRastreio, sessao: Banco, ctx: Ctx, chave: Chave = None):
    viagem = viagens.viagem_acessivel(sessao, ctx, codigo, "integrar" if ctx.integracao else "operar", escrita=True)

    def aplicar():
        viagens.iniciar_rastreio(sessao, ctx, viagem, dados.source, dados.version)
        return resposta_rastreio(sessao, ctx, viagem)

    return mutacao(sessao, ctx, chave, f"iniciar-rastreio:{viagem.id}", dados, aplicar)


@router.post("/viagens/{codigo}/rastreio/encerrar")
def encerrar_rastreio(codigo: str, dados: EncerrarRastreio, sessao: Banco, ctx: Ctx, chave: Chave = None):
    viagem = viagens.viagem_acessivel(sessao, ctx, codigo, "integrar" if ctx.integracao else "operar", escrita=True)

    def aplicar():
        viagens.encerrar_rastreio(sessao, ctx, viagem, dados.version, dados.reason)
        return resposta_rastreio(sessao, ctx, viagem)

    return mutacao(sessao, ctx, chave, f"encerrar-rastreio:{viagem.id}", dados, aplicar)


def resposta_rastreio(sessao, ctx, viagem):
    if "consultar" in ctx.permissoes:
        return viagens.dados_viagem(sessao, ctx, viagem)
    fonte = viagens.fonte_ativa(sessao, viagem)
    return {"id": viagem.codigo, "version": viagem.versao, "source": fonte.fonte if fonte else None}


@router.get("/viagens/{codigo}/posicoes")
def listar_posicoes(codigo: str, sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 500,
                    de: Annotated[datetime | None, Query(alias="from")] = None,
                    ate: Annotated[datetime | None, Query(alias="to")] = None):
    viagem = viagens.viagem_acessivel(sessao, ctx, codigo)
    return viagens.listar_posicoes(sessao, ctx, viagem, offset, limit,
                                  instante(de) if de else None, instante(ate) if ate else None)


@router.post("/viagens/{codigo}/posicoes", status_code=201)
def inserir_posicao(codigo: str, dados: Posicao, sessao: Banco, ctx: Ctx, chave: Chave = None):
    viagem = viagens.viagem_acessivel(sessao, ctx, codigo, "integrar" if ctx.integracao else "operar", escrita=True)
    return mutacao(sessao, ctx, chave, f"inserir-posicao:{viagem.id}", dados,
                   lambda: viagens.inserir_posicao(sessao, ctx, viagem, dados_editaveis(dados)))


@router.post("/sincronizar")
def sincronizar(sessao: Banco, ctx: Ctx, dados: Sincronizar | None = None):
    if ctx.integracao:
        exigir(ctx, "integrar")
        if ctx.integracao.recurso_tipo and ctx.integracao.recurso_tipo != "sensor":
            erro(403, "O escopo da integração não permite sincronizar sensores.")
    elif "integrar" not in ctx.permissoes:
        exigir(ctx, "operar")
    with transacao(sessao):
        return monitor.sincronizar(sessao, ctx, dados.sensorId if dados else None,
                                   instante(dados.fromDate) if dados and dados.fromDate else None)


@router.get("/alertas")
def alertas(sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    return monitor.listar_alertas(sessao, ctx, offset, limit)


@router.post("/alertas/{alerta_id}/tratar")
def tratar_alerta(alerta_id: int, dados: TratarOcorrencia, sessao: Banco, ctx: Ctx, chave: Chave = None):
    exigir(ctx, "operar")
    alerta = sessao.get(Ocorrencia, alerta_id)
    if alerta is None:
        log_security_block(
            "IDOR",
            "tentativa_tratar_alerta_inexistente",
            user_id=ctx.conta.id if ctx.conta else None,
            resource_id=alerta_id,
        )
        erro(404, "Ocorrência indisponível.")
    lote = sessao.get(LoteOperacional, alerta.lote_id)
    _, comp = lote_acessivel(sessao, ctx, lote.codigo, "operar")
    if not monitor.alerta_visivel(alerta, comp):
        log_security_block(
            "IDOR",
            "tentativa_tratar_alerta_alheio",
            user_id=ctx.conta.id if ctx.conta else None,
            resource_id=alerta_id,
        )
        erro(404, "Ocorrência indisponível.")

    def aplicar():
        conferir_versao(alerta, dados.version)
        if alerta.estado == "resolvida" and dados.status != "resolvida":
            erro(409, "A ocorrência já está resolvida.")
        alerta.estado = dados.status
        alerta.versao += 1
        registrar_evento(sessao, ctx, lote, "Ocorrência tratada", agora_utc(), lote.fase, dados.reason,
                         {"ocorrenciaId": alerta.id, "estado": dados.status})
        return monitor.dados_alerta(sessao, alerta)

    return mutacao(sessao, ctx, chave, f"tratar-alerta:{alerta_id}", dados, aplicar, comp)


@router.get("/configuracoes/fluxo")
def configuracao(sessao: Banco, ctx: Ctx):
    exigir(ctx, "administrar")
    return fluxo.obter_fluxo(sessao, ctx.empresa.id)


@router.patch("/configuracoes/fluxo")
def configurar(dados: ConfigurarFluxo, sessao: Banco, ctx: Ctx, chave: Chave = None):
    exigir(ctx, "administrar")
    return mutacao(sessao, ctx, chave, "configurar-fluxo", dados, lambda: fluxo.atualizar_fluxo(
        sessao, ctx, dados_editaveis(dados, {"absenceMinutes", "departureDetection"}),
    ))


@router.get("/compartilhamentos")
def compartilhamentos_recebidos(sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "consultar")
    return fluxo.listar_compartilhamentos(sessao, ctx)


@router.get("/lotes/{codigo}/compartilhamentos")
def compartilhamentos_enviados(codigo: str, sessao: Banco, ctx: Ctx):
    lote, _ = lote_acessivel(sessao, ctx, codigo, "compartilhar")
    return fluxo.listar_compartilhamentos(sessao, ctx, lote)


@router.post("/lotes/{codigo}/compartilhamentos", status_code=201)
def criar_compartilhamento(codigo: str, dados: Compartilhar, sessao: Banco, ctx: Ctx, chave: Chave = None):
    lote, _ = lote_acessivel(sessao, ctx, codigo, "compartilhar")
    return mutacao(sessao, ctx, chave, f"compartilhar:{lote.id}", dados,
                   lambda: fluxo.compartilhar(sessao, ctx, lote, dados_editaveis(dados)))


@router.post("/compartilhamentos/{comp_id}/aceitar")
def aceitar_compartilhamento(comp_id: int, sessao: Banco, ctx: Ctx):
    exigir_humano(ctx)
    exigir(ctx, "consultar")
    with transacao(sessao):
        return fluxo.aceitar_compartilhamento(sessao, ctx, comp_id)


@router.delete("/lotes/{codigo}/compartilhamentos/{comp_id}")
def revogar_compartilhamento(codigo: str, comp_id: int, sessao: Banco, ctx: Ctx):
    lote, _ = lote_acessivel(sessao, ctx, codigo, "compartilhar")
    with transacao(sessao):
        return fluxo.revogar_compartilhamento(sessao, ctx, lote, comp_id)


@router.get("/publico/{codigo}")
def resumo_publico(codigo: str, sessao: Banco):
    return monitor.resumo_publico(sessao, codigo)


@router.get("/lotes/{codigo}/laudo")
def laudo_operacional(codigo: str, sessao: Banco, ctx: Ctx, resposta: Response):
    resposta.headers["Cache-Control"] = "no-store"
    lote, comp = lote_acessivel(sessao, ctx, codigo)
    dados = monitor.laudo(sessao, lote, comp)
    if comp is None:
        revisoes = monitor.revisoes_laudo(sessao, lote, limit=1)
        dados["latestIssuedRevision"] = revisoes[0] if revisoes else None
        dados["hasUnissuedChanges"] = not revisoes or (
            (dados["version"], dados["readingCount"]) != (revisoes[0]["version"], revisoes[0]["readingCount"])
        )
    return dados


@router.get("/lotes/{codigo}/laudo/revisoes")
def revisoes_laudo(codigo: str, sessao: Banco, ctx: Ctx, offset: Deslocamento = 0, limit: Pagina = 100):
    lote, _ = lote_acessivel(sessao, ctx, codigo)
    dono(ctx, lote)
    return monitor.revisoes_laudo(sessao, lote, offset, limit)


@router.get("/lotes/{codigo}/laudo/revisoes/{revisao_id}")
def detalhe_revisao_laudo(codigo: str, revisao_id: int, sessao: Banco, ctx: Ctx):
    lote, _ = lote_acessivel(sessao, ctx, codigo)
    dono(ctx, lote)
    return monitor.consultar_revisao_laudo(sessao, lote, revisao_id)


@router.post("/lotes/{codigo}/laudo", status_code=201)
def emitir_laudo(codigo: str, dados: EmitirLaudo, sessao: Banco, ctx: Ctx, resposta: Response):
    resposta.headers["Cache-Control"] = "no-store"
    lote, _ = lote_acessivel(sessao, ctx, codigo, "compartilhar")
    dono(ctx, lote)
    with transacao(sessao):
        return monitor.emitir_laudo(sessao, ctx, lote, dados.expiresAt, dados.reason)


@router.delete("/lotes/{codigo}/laudo", status_code=204)
def revogar_laudo(codigo: str, sessao: Banco, ctx: Ctx):
    lote, _ = lote_acessivel(sessao, ctx, codigo, "compartilhar")
    dono(ctx, lote)
    with transacao(sessao):
        monitor.revogar_laudos(sessao, ctx, lote)
    return Response(status_code=204)


@router.get("/laudos/{token}")
def laudo_secreto(token: str, sessao: Banco, resposta: Response):
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return monitor.laudo_secreto(sessao, token)
