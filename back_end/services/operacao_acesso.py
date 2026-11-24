"""Autorização de recursos, autoria e transações da API operacional."""

import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta, timezone
from itertools import islice

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError

from models.contas import Empresa
from models.operacao import ComandoOperacional, CompartilhamentoLote, EventoLote, LoteOperacional
from security.audit_log import log_security_block
from services.acessos import exigir
from services.datas import agora_utc, para_utc


def erro(status, detalhe):
    raise HTTPException(status_code=status, detail=detalhe)


def utc(data):
    if data is None:
        return None
    return data.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def instante(data=None):
    if data is None:
        return agora_utc()
    if data.tzinfo is None or data.utcoffset() is None:
        erro(422, "Informe o horário com indicação de fuso.")
    return para_utc(data)


def efetivo(data=None):
    horario = instante(data)
    if horario > agora_utc() + timedelta(minutes=5):
        erro(422, "O horário efetivo está no futuro.")
    return horario


def conferir_versao(registro, esperada):
    if esperada is not None and registro.versao != esperada:
        erro(409, "O registro mudou. Recarregue os dados antes de continuar.")


@contextmanager
def transacao(sessao):
    try:
        yield
        sessao.commit()
    except (IntegrityError, StaleDataError):
        sessao.rollback()
        erro(409, "O registro já existe ou foi alterado durante a operação.")
    except OperationalError as exc:
        sessao.rollback()
        if "locked" in str(exc.orig).lower():
            erro(409, "Houve uma alteração concorrente. Tente novamente.")
        raise


def confirmar(sessao):
    with transacao(sessao):
        pass


def escopo(ctx, tipo, identificador=None):
    integracao = ctx.integracao
    return not integracao or not integracao.recurso_tipo or (
        tipo == integracao.recurso_tipo and str(identificador) == integracao.recurso_id
    )


def exigir_escopo(ctx, tipo, identificador=None):
    if not escopo(ctx, tipo, identificador):
        erro(404, "Recurso indisponível.")


def empresa_ativa(sessao, empresa_id):
    empresa = sessao.get(Empresa, empresa_id)
    if empresa is None or not empresa.ativo:
        erro(404, "Empresa indisponível.")
    return empresa


def identificar(ctx):
    if ctx.integracao:
        return f"integracao:{ctx.integracao.id}", ctx.integracao.nome
    return f"conta:{ctx.conta.id}", ctx.conta.nome


def executar(sessao, ctx, chave, acao, payload, executar_comando, comp=None):
    """Publica o resultado junto com o efeito para repetir comandos com segurança."""
    if not chave:
        if ctx.integracao:
            erro(422, "Informe o cabeçalho Idempotency-Key para executar a operação.")
        return executar_comando()
    chave = chave.strip()
    if not chave or len(chave) > 128:
        erro(422, "A chave de idempotência deve ter entre 1 e 128 caracteres.")
    ator, _ = identificar(ctx)
    registro_id = (ctx.empresa.id, ator, chave)
    recurso_integracao = (ctx.integracao.recurso_tipo, ctx.integracao.recurso_id) if ctx.integracao else None
    direitos_lote = (comp.id, comp.versao) if comp else None
    assinatura = hashlib.sha256(json.dumps(
        [acao, payload, ctx.papel, sorted(ctx.permissoes), recurso_integracao, direitos_lote],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()

    def reproduzir(registro):
        if registro.assinatura != assinatura:
            erro(409, "A chave de idempotência já foi usada com outro comando ou outro acesso.")
        return registro.resultado

    anterior = sessao.get(ComandoOperacional, registro_id)
    if anterior:
        return reproduzir(anterior)
    registro = ComandoOperacional(
        empresa_id=ctx.empresa.id, ator=ator, chave=chave, assinatura=assinatura,
        resultado={}, registrado_em=agora_utc(),
    )
    sessao.add(registro)
    try:
        sessao.flush()
    except IntegrityError:
        sessao.rollback()
        anterior = sessao.get(ComandoOperacional, registro_id)
        if anterior:
            return reproduzir(anterior)
        erro(409, "O comando está sendo registrado. Tente novamente.")
    resultado = executar_comando()
    registro.resultado = resultado
    return resultado


def comp_ativo(agora):
    return (
        CompartilhamentoLote.aceito_em.is_not(None),
        CompartilhamentoLote.revogado_em.is_(None),
        CompartilhamentoLote.expira_em > agora,
    )


def lotes_visiveis(sessao, ctx, codigo=None, viagem_id=None, offset=None, limit=None, somente_consulta=True,
                   busca=None, fase=None):
    if somente_consulta and "consultar" not in ctx.permissoes:
        return []
    agora = agora_utc()
    comp = select(CompartilhamentoLote.lote_id).where(
        CompartilhamentoLote.empresa_id == ctx.empresa.id, *comp_ativo(agora),
    )
    filtros = [LoteOperacional.id.in_(comp)]
    if ctx.papel != "cliente":
        filtros.append(LoteOperacional.empresa_id == ctx.empresa.id)
    consulta = select(LoteOperacional).where(or_(*filtros)).order_by(LoteOperacional.id.desc())
    if codigo is not None:
        consulta = consulta.where(LoteOperacional.codigo == codigo_operacional(codigo))
    if viagem_id is not None:
        consulta = consulta.where(LoteOperacional.viagem_id == viagem_id)
    if fase is not None:
        consulta = consulta.where(LoteOperacional.fase == fase)
    integracao = ctx.integracao
    if integracao and integracao.recurso_tipo:
        if integracao.recurso_tipo != "lote":
            return []
        consulta = consulta.where(LoteOperacional.codigo == integracao.recurso_id)
    termo = (busca or "").strip().casefold()
    if termo:
        candidatos = sessao.scalars(consulta.execution_options(yield_per=100))
        encontrados = (lote for lote in candidatos if termo in " ".join(
            (lote.codigo, lote.fruta_nome, lote.variedade, lote.cliente),
        ).casefold())
        primeiro = offset or 0
        return list(islice(encontrados, primeiro, primeiro + limit if limit is not None else None))
    if offset is not None:
        consulta = consulta.offset(offset)
    if limit is not None:
        consulta = consulta.limit(limit)
    return list(sessao.scalars(consulta))


def codigo_operacional(codigo):
    normalizado = codigo.upper()
    numero = normalizado.removeprefix("PS")
    if len(numero) <= 18 and numero.isascii() and numero.isdecimal():
        return f"PS-{int(numero):04d}"
    return normalizado


def concessao(sessao, ctx, lote):
    if lote.empresa_id == ctx.empresa.id and ctx.papel != "cliente":
        return None
    vinculo = sessao.scalar(select(CompartilhamentoLote).where(
        CompartilhamentoLote.lote_id == lote.id,
        CompartilhamentoLote.empresa_id == ctx.empresa.id,
        *comp_ativo(agora_utc()),
    ))
    if vinculo is None or "consultar" not in vinculo.direitos:
        erro(404, "Lote indisponível.")
    return vinculo


def lote_acessivel(sessao, ctx, codigo, permissao="consultar"):
    recebe_por_concessao = ctx.papel == "cliente" and permissao == "receber"
    exigir(ctx, "consultar" if recebe_por_concessao else permissao)
    lotes = lotes_visiveis(sessao, ctx, codigo=codigo, limit=1, somente_consulta=False)
    if not lotes:
        log_security_block(
            "IDOR",
            "tentativa_acesso_lote_alheio_ou_inexistente",
            user_id=ctx.conta.id if ctx.conta else None,
            resource_id=codigo,
        )
        erro(404, "Lote indisponível.")
    lote = lotes[0]
    comp = concessao(sessao, ctx, lote)
    if permissao != "consultar" and comp and permissao not in comp.direitos:
        log_security_block(
            "IDOR",
            "tentativa_acao_lote_sem_permissao",
            user_id=ctx.conta.id if ctx.conta else None,
            resource_id=codigo,
        )
        erro(403, "A ação não faz parte dos direitos concedidos neste lote.")
    return lote, comp


def dono(ctx, lote):
    if ctx.empresa.id != lote.empresa_id or ctx.papel == "cliente":
        log_security_block(
            "IDOR",
            "tentativa_acao_lote_titular_alheio",
            user_id=ctx.conta.id if ctx.conta else None,
            resource_id=lote.codigo,
        )
        erro(403, "A ação exige autorização da empresa titular do lote.")


def registrar_evento(sessao, ctx, lote, tipo, data, anterior=None, motivo=None, dados=None, automatica=False):
    _, nome = identificar(ctx)
    evento = EventoLote(
        lote_id=lote.id, tipo=tipo, autor_id=ctx.conta.id if ctx.conta and not automatica else None,
        integracao_id=ctx.integracao.id if ctx.integracao else None,
        empresa_id=ctx.empresa.id, empresa_nome=ctx.empresa.nome,
        autor_nome="Automação PlantSync" if automatica else nome,
        efetivo_em=data, registrado_em=agora_utc(), fase_anterior=anterior,
        fase_atual=lote.fase, motivo=motivo, dados=dados or {},
    )
    sessao.add(evento)
    return evento
