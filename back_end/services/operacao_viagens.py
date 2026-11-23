"""Viagens, recortes de rota e ingestão autorizada de posições."""

from datetime import timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from secrets import token_hex

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update

from models.operacao import FontePosicao, LoteOperacional, Parada, Permanencia, PosicaoViagem, Viagem
from services.acessos import exigir
from services.datas import agora_utc
from services.operacao import mover, obter_fluxo, papel_permitido, permanencias
from services.operacao_acesso import (
    conferir_versao, concessao, efetivo, erro, escopo, exigir_escopo, identificar, lotes_visiveis,
    registrar_evento, utc,
)
from services.operacao_monitoramento import ocorrencia


def viagem_propria(ctx, viagem):
    return viagem.empresa_id == ctx.empresa.id and ctx.papel != "cliente"


def lotes_da_rota(sessao, ctx, viagem):
    if ctx.integracao and ctx.integracao.recurso_tipo == "viagem" and viagem_propria(ctx, viagem):
        return []
    return [(lote, comp) for lote in lotes_visiveis(sessao, ctx, viagem_id=viagem.id)
            if not (comp := concessao(sessao, ctx, lote)) or "rota" in comp.direitos]


def viagem_acessivel(sessao, ctx, codigo, permissao="consultar", escrita=False):
    exigir(ctx, permissao)
    codigo = codigo.upper()
    exigir_escopo(ctx, "viagem", codigo)
    viagem = sessao.scalar(select(Viagem).where(Viagem.codigo == codigo))
    if viagem is None:
        erro(404, "Viagem indisponível.")
    proprie = viagem_propria(ctx, viagem)
    if not proprie and (escrita or not lotes_da_rota(sessao, ctx, viagem)):
        erro(404, "Viagem indisponível.")
    return viagem


def nova_viagem(sessao, ctx, dados):
    codigo = dados.get("id") or f"V-{token_hex(4).upper()}"
    exigir_escopo(ctx, "viagem", codigo)
    viagem = Viagem(
        empresa_id=ctx.empresa.id, codigo=codigo, veiculo=dados["vehicle"],
        transportadora=dados["carrier"], responsavel=dados["responsible"], origem=dados.get("origin", ""),
        fonte=dados.get("source"), criado_em=efetivo(dados.get("createdAt")),
    )
    sessao.add(viagem)
    sessao.flush()
    for ordem, parada in enumerate(dados.get("stops", []), 1):
        sessao.add(Parada(viagem_id=viagem.id, ordem=ordem, nome=parada["name"]))
    return viagem


def fonte_ativa(sessao, viagem):
    return sessao.scalar(select(FontePosicao).where(
        FontePosicao.viagem_id == viagem.id, FontePosicao.fim.is_(None),
    ).order_by(FontePosicao.id.desc()).limit(1))


def recortes_da_rota(sessao, viagem, lotes):
    for lote, comp in lotes:
        for trecho in permanencias(sessao, lote):
            if trecho.fase != 2 or trecho.viagem_id != viagem.id:
                continue
            inicio = max(trecho.inicio, comp.inicio_dados) if comp and comp.inicio_dados else trecho.inicio
            fim = min(filter(None, [trecho.fim, comp.fim_dados if comp else None]), default=None)
            if fim is None or fim > inicio:
                yield inicio, fim


def consulta_posicoes(sessao, ctx, viagem, lotes):
    consulta = select(PosicaoViagem).where(PosicaoViagem.viagem_id == viagem.id)
    if not viagem_propria(ctx, viagem):
        recortes = list(recortes_da_rota(sessao, viagem, lotes))
        if not recortes:
            return consulta.where(False)
        consulta = consulta.where(or_(*[
            PosicaoViagem.medida_em >= inicio if fim is None else
            and_(PosicaoViagem.medida_em >= inicio, PosicaoViagem.medida_em < fim)
            for inicio, fim in recortes
        ]))
    return consulta.where(PosicaoViagem.medida_em <= agora_utc())


def posicao_json(posicao, quebra=False):
    return {"id": posicao.id, "entryId": posicao.entrada, "latitude": posicao.latitude,
            "longitude": posicao.longitude, "accuracy": posicao.precisao,
            "measuredAt": utc(posicao.medida_em), "receivedAt": utc(posicao.recebida_em),
            "source": posicao.fonte, "sourceId": posicao.fonte_id, "break": quebra}


def listar_posicoes(sessao, ctx, viagem, offset, limit, inicio=None, fim=None):
    if inicio and fim and fim <= inicio:
        erro(422, "Informe um fim posterior ao início.")
    lotes = lotes_da_rota(sessao, ctx, viagem)
    consulta = consulta_posicoes(sessao, ctx, viagem, lotes)
    if inicio:
        consulta = consulta.where(PosicaoViagem.medida_em >= inicio)
    if fim:
        consulta = consulta.where(PosicaoViagem.medida_em < fim)
    total = sessao.scalar(select(func.count()).select_from(consulta.subquery()))
    posicoes = sessao.scalars(consulta.order_by(PosicaoViagem.medida_em, PosicaoViagem.id).offset(offset).limit(limit))
    items = []
    anterior = None
    recortes = None if viagem_propria(ctx, viagem) else list(recortes_da_rota(sessao, viagem, lotes))
    for posicao in posicoes:
        sem_trecho_continuo = (recortes is not None and anterior and not any(
            de <= anterior.medida_em and (ate is None or posicao.medida_em < ate) for de, ate in recortes
        ))
        quebra = (anterior is None or anterior.fonte_id != posicao.fonte_id or
                  posicao.medida_em - anterior.medida_em > timedelta(minutes=15) or sem_trecho_continuo)
        items.append(posicao_json(posicao, bool(quebra)))
        anterior = posicao
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def dados_viagem(sessao, ctx, viagem):
    propria = viagem_propria(ctx, viagem)
    lotes = lotes_da_rota(sessao, ctx, viagem)
    paradas = select(Parada).where(Parada.viagem_id == viagem.id).order_by(Parada.ordem)
    if not propria:
        paradas = paradas.where(Parada.id.in_([lote.parada_id for lote, _ in lotes if lote.parada_id]))
    consulta = consulta_posicoes(sessao, ctx, viagem, lotes)
    ultima = sessao.scalar(consulta.order_by(PosicaoViagem.medida_em.desc(), PosicaoViagem.id.desc()).limit(1))
    fonte = fonte_ativa(sessao, viagem) if propria else None
    fases = {lote.fase for lote, _ in lotes}
    fase = 2 if 2 in fases else 1 if 1 in fases else 3 if fases == {3} else 0
    return {"id": viagem.codigo, "name": viagem.codigo,
            "vehicle": viagem.veiculo if propria else None,
            "carrier": viagem.transportadora if propria else None,
            "responsible": viagem.responsavel if propria else None,
            "origin": viagem.origem if propria else None, "phase": fase,
            "version": viagem.versao, "source": fonte.fonte if fonte else ultima.fonte if ultima else None,
            "createdAt": utc(viagem.criado_em) if propria else None,
            "stops": [{"id": p.id, "name": p.nome, "order": p.ordem if propria else i,
                       "lotIds": [lote.codigo for lote, _ in lotes if lote.parada_id == p.id]}
                      for i, p in enumerate(sessao.scalars(paradas), 1)],
            "lotIds": [lote.codigo for lote, _ in lotes], "latestPosition": posicao_json(ultima) if ultima else None,
            "tracking": {"id": fonte.id, "source": fonte.fonte, "startedAt": utc(fonte.inicio),
                         "actor": fonte.autor_nome} if fonte else None,
            "permissions": sorted(ctx.permissoes & {"operar", "integrar"}) if propria else []}


def listar_viagens(sessao, ctx, offset, limit):
    exigir(ctx, "consultar")
    ids_compartilhados = {l.viagem_id for l in lotes_visiveis(sessao, ctx) if l.viagem_id}
    filtros = [Viagem.id.in_(ids_compartilhados)]
    if ctx.papel != "cliente":
        filtros.append(Viagem.empresa_id == ctx.empresa.id)
    consulta = select(Viagem).where(or_(*filtros)).order_by(Viagem.id.desc())
    viagens = [viagem for viagem in sessao.scalars(consulta)
               if escopo(ctx, "viagem", viagem.codigo) and
               (viagem_propria(ctx, viagem) or lotes_da_rota(sessao, ctx, viagem))]
    return [dados_viagem(sessao, ctx, v) for v in viagens[offset:offset + limit]]


def reservar_viagem(sessao, viagem):
    # Inicia a escrita antes de ler a fonte ou abrir savepoints no SQLite.
    # Uma posição comum fica registrada sem invalidar formulários de despacho.
    sessao.execute(update(Viagem).where(Viagem.id == viagem.id).values(versao=Viagem.versao))
    sessao.refresh(viagem)


def despachar_viagem(sessao, ctx, viagem, dados):
    reservar_viagem(sessao, viagem)
    conferir_versao(viagem, dados.get("version"))
    data = efetivo(dados.get("effectiveAt"))
    lotes = list(sessao.scalars(select(LoteOperacional).where(
        LoteOperacional.viagem_id == viagem.id, LoteOperacional.empresa_id == ctx.empresa.id,
    ).order_by(LoteOperacional.id)))
    resultado = {"id": viagem.codigo, "dispatched": [], "skipped": []}
    for lote in lotes:
        if lote.fase != 1:
            resultado["skipped"].append({"id": lote.codigo, "reason": "O lote não aguarda despacho."})
            continue
        try:
            with sessao.begin_nested():
                mover(sessao, ctx, lote, "despachar", {**dados, "version": None,
                                                       "effectiveAt": data.replace(tzinfo=timezone.utc)},
                      atualizar_viagem=False)
        except HTTPException as exc:
            resultado["skipped"].append({"id": lote.codigo, "reason": exc.detail})
        else:
            resultado["dispatched"].append(lote.codigo)
    if resultado["dispatched"]:
        viagem.versao += 1
    resultado["version"] = viagem.versao
    return resultado


def iniciar_rastreio(sessao, ctx, viagem, fonte, versao):
    conferir_versao(viagem, versao)
    if ctx.integracao and fonte != "externa":
        erro(403, "Uma integração deve usar uma fonte externa.")
    ator, nome = identificar(ctx)
    ativa = fonte_ativa(sessao, viagem)
    if ativa:
        if (ativa.fonte, ativa.ator) == (fonte, ator):
            return
        erro(409, "Encerre a fonte vigente antes de ativar outra.")
    agora = agora_utc()
    sessao.add(FontePosicao(viagem_id=viagem.id, fonte=fonte, ator=ator, autor_nome=nome, inicio=agora))
    viagem.fonte = fonte
    viagem.versao += 1


def encerrar_rastreio(sessao, ctx, viagem, versao, motivo):
    conferir_versao(viagem, versao)
    fonte = fonte_ativa(sessao, viagem)
    if fonte:
        if ctx.integracao and fonte.ator != identificar(ctx)[0]:
            erro(403, "A credencial só pode encerrar sua própria fonte de rastreio.")
        fonte.fim = agora_utc()
        fonte.motivo_fim = motivo
        viagem.fonte = None
        viagem.versao += 1


def distancia_m(lat1, lon1, lat2, lon2):
    angulo = sin(radians(lat2 - lat1) / 2) ** 2
    angulo += cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 12_742_000 * asin(sqrt(min(1, angulo)))


def evidenciar_saida(sessao, ctx, viagem, fonte, atual):
    lotes = sessao.scalars(select(LoteOperacional).where(
        LoteOperacional.viagem_id == viagem.id, LoteOperacional.fase == 1,
    ).order_by(LoteOperacional.id))
    agora = agora_utc()
    for lote in list(lotes):
        fluxo = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)
        regras = fluxo["departureDetection"]
        if not regras or atual.medida_em > agora or agora - atual.medida_em > timedelta(minutes=regras["maxAgeMinutes"]):
            continue
        registros = list(sessao.scalars(select(PosicaoViagem).where(
            PosicaoViagem.viagem_id == viagem.id, PosicaoViagem.fonte_id == fonte.id,
            PosicaoViagem.medida_em >= lote.carregado_em,
            PosicaoViagem.medida_em <= agora,
        ).order_by(PosicaoViagem.medida_em.desc(), PosicaoViagem.id.desc()).limit(1000)))
        if not registros or registros[0].id != atual.id:
            continue
        fora, interna = [], None
        for pos in registros:
            if pos.precisao is None or pos.precisao > regras["maxAccuracyMeters"]:
                break
            distancia = distancia_m(regras["latitude"], regras["longitude"], pos.latitude, pos.longitude)
            if distancia - pos.precisao > regras["radiusMeters"]:
                fora.append(pos)
            else:
                if distancia + pos.precisao <= regras["radiusMeters"]:
                    interna = pos
                break
        if interna is None or len(fora) < 2:
            continue
        primeira = fora[-1]
        duracao = (atual.medida_em - primeira.medida_em).total_seconds()
        max_intervalo = timedelta(minutes=regras["maxAgeMinutes"])
        if duracao < regras["persistenceSeconds"] or any(
            a.medida_em - b.medida_em > max_intervalo for a, b in zip(fora, [*fora[1:], interna])
        ):
            continue
        chave = f"saida:{lote.id}:{viagem.id}:{utc(lote.carregado_em)}"
        alerta = ocorrencia(sessao, lote, chave, "saida", primeira.medida_em,
                            "Saída detectada após a sequência de posições fora da área configurada.")
        dados = {"positionId": primeira.id, "lastPositionId": atual.id, "insidePositionId": interna.id,
                 "trackingSourceId": fonte.id}
        if alerta.fim is None:
            alerta.fim = atual.medida_em
            lote.versao += 1
            registrar_evento(sessao, ctx, lote, "Saída detectada", primeira.medida_em, lote.fase,
                             dados=dados, automatica=True)
        if fluxo["automatic"] and papel_permitido(fluxo, "automacao", "despachar") and not lote.transferencia_pendente_id and duracao >= max(
            regras["persistenceSeconds"], regras["autoDelaySeconds"],
        ):
            mover(sessao, ctx, lote, "despachar", {"effectiveAt": primeira.medida_em.replace(tzinfo=timezone.utc),
                                                  "evidence": dados}, automatica=True)


def inserir_posicao(sessao, ctx, viagem, dados):
    reservar_viagem(sessao, viagem)
    medida = efetivo(dados["measuredAt"])
    ator, _ = identificar(ctx)
    fonte = sessao.scalar(select(FontePosicao).where(
        FontePosicao.viagem_id == viagem.id, FontePosicao.fonte == dados["source"], FontePosicao.ator == ator,
        FontePosicao.inicio <= medida, or_(FontePosicao.fim.is_(None), FontePosicao.fim > medida),
    ).order_by(FontePosicao.id.desc()).limit(1))
    if fonte is None:
        erro(409, "Não havia uma fonte de rastreio autorizada para este ator no horário da posição.")
    anterior = sessao.scalar(select(PosicaoViagem).where(
        PosicaoViagem.viagem_id == viagem.id, PosicaoViagem.fonte_id == fonte.id,
        PosicaoViagem.entrada == dados["entryId"],
    ))
    atributos = dict(medida_em=medida, latitude=dados["latitude"], longitude=dados["longitude"],
                     precisao=dados.get("accuracy"))
    if anterior:
        if any(getattr(anterior, atributo) != valor for atributo, valor in atributos.items()):
            erro(409, "A identificação desta posição já foi usada com dados diferentes.")
        return posicao_json(anterior)
    posicao = PosicaoViagem(viagem_id=viagem.id, fonte_id=fonte.id, fonte=fonte.fonte,
                           entrada=dados["entryId"], recebida_em=agora_utc(), **atributos)
    sessao.add(posicao)
    sessao.flush()
    evidenciar_saida(sessao, ctx, viagem, fonte, posicao)
    return posicao_json(posicao)
