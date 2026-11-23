"""Fluxo dos lotes, responsabilidade e compartilhamento entre empresas."""

from datetime import timedelta
from secrets import token_hex, token_urlsafe

from sqlalchemy import func, or_, select

from models.contas import Empresa
from models.operacao import (
    Ambiente, CompartilhamentoLote, EventoLote, FluxoVersao, LoteOperacional,
    Parada, Permanencia, Viagem,
)
from services.acessos import exigir
from services.catalogo import fruta_disponivel
from services.datas import agora_utc
from services.operacao_acesso import (
    comp_ativo, conferir_versao, concessao, dono, efetivo, empresa_ativa, erro,
    exigir_escopo, instante, lotes_visiveis, registrar_evento, utc,
)


FLUXO_PADRAO = {
    "transferAt": "carregamento", "requireAcceptance": False, "automatic": False,
    "absenceMinutes": None, "departureDetection": None, "allowedRolesByAction": {},
}
TRANSICOES = {"carregar": (0, 1), "despachar": (1, 2), "receber": (2, 3)}
EVENTOS_COMPARTILHADOS = (
    "Preparação iniciada", "Ambiente de preparação alterado", "Carregamento registrado",
    "Despacho confirmado", "Despacho provisório", "Despacho validado", "Recebimento registrado",
    "Retorno de fase", "Transferência confirmada", "Saída detectada", "Importação do legado",
)


def obter_fluxo(sessao, empresa_id, versao=None):
    consulta = select(FluxoVersao).where(FluxoVersao.empresa_id == empresa_id)
    if versao is not None:
        consulta = consulta.where(FluxoVersao.versao == versao)
    registro = sessao.scalar(consulta.order_by(FluxoVersao.versao.desc()).limit(1))
    return {**FLUXO_PADRAO, **(registro.configuracao if registro else {}),
            "version": registro.versao if registro else 0}


def atualizar_fluxo(sessao, ctx, dados):
    exigir(ctx, "administrar")
    atual = obter_fluxo(sessao, ctx.empresa.id)
    versao = atual.pop("version")
    if dados.pop("version", versao) != versao:
        erro(409, "A configuração mudou. Recarregue os dados.")
    configuracao = {**atual, **dados}
    if configuracao["automatic"] and not configuracao["departureDetection"]:
        erro(422, "Defina os critérios de detecção de saída antes do avanço automático.")
    sessao.add(FluxoVersao(
        empresa_id=ctx.empresa.id, versao=versao + 1, configuracao=configuracao,
        criado_em=agora_utc(), autor_id=ctx.conta.id,
    ))
    return {**configuracao, "version": versao + 1}


def papel_permitido(configuracao, papel, acao):
    papeis = configuracao["allowedRolesByAction"].get(acao)
    return papeis is None or papel in papeis


def exigir_acao_fluxo(configuracao, papel, acao):
    if not papel_permitido(configuracao, papel, acao):
        erro(403, "A configuração de fluxo aplicada ao lote não permite esta ação para o papel atual.")


def ambiente_da_empresa(sessao, ctx, ambiente_id, tipo=None):
    ambiente = sessao.get(Ambiente, ambiente_id) if ambiente_id is not None else None
    if ambiente is None or ambiente.empresa_id != ctx.empresa.id:
        erro(404, "Ambiente indisponível.")
    if tipo and ambiente.tipo != tipo:
        erro(422, "O tipo de ambiente é incompatível com esta etapa.")
    return ambiente


def nova_permanencia(sessao, lote, data):
    sessao.add(Permanencia(
        lote_id=lote.id, ambiente_id=lote.ambiente_id, fase=lote.fase,
        responsavel_empresa_id=lote.responsavel_empresa_id,
        responsavel_nome=lote.responsavel_nome, inicio=data, viagem_id=lote.viagem_id,
    ))


def permanencias(sessao, lote):
    return list(sessao.scalars(select(Permanencia).where(Permanencia.lote_id == lote.id).order_by(
        Permanencia.inicio, Permanencia.id,
    )))


def encerrar_permanencia(sessao, lote, data):
    anterior = sessao.scalar(select(Permanencia).where(
        Permanencia.lote_id == lote.id, Permanencia.fim.is_(None),
    ).order_by(Permanencia.id.desc()).limit(1))
    if anterior:
        if data < anterior.inicio:
            erro(409, "O horário antecede o início da etapa atual.")
        anterior.fim = data
    elif data < (lote.recebido_em or lote.despachado_em or lote.carregado_em or lote.preparado_em):
        erro(409, "O horário antecede a movimentação que está sendo corrigida.")


def novo_lote(sessao, ctx, dados):
    exigir(ctx, "operar")
    codigo = dados.get("id") or f"PS-{token_hex(4).upper()}"
    exigir_escopo(ctx, "lote", codigo)
    fruta = fruta_disponivel(sessao, ctx.empresa.id, dados["fruitId"])
    ambiente = ambiente_da_empresa(sessao, ctx, dados["environmentId"], "camara")
    configuracao = obter_fluxo(sessao, ctx.empresa.id)
    exigir_acao_fluxo(configuracao, ctx.papel, "preparar")
    data = efetivo(dados.get("preparedAt"))
    faixa = dados.get("range") or [fruta.temp_min_c, fruta.temp_max_c]
    motivo = dados.get("reason")
    if dados.get("range") and not motivo:
        erro(422, "Justifique a faixa específica do lote.")
    lote = LoteOperacional(
        codigo=codigo, empresa_id=ctx.empresa.id, codigo_publico=token_urlsafe(18),
        fruta_id=fruta.id, fruta_nome=fruta.nome, variedade=dados.get("variety", ""),
        cliente=dados["client"], destino=dados["destination"],
        origem=dados.get("origin", ""), produtor=dados.get("producer") or ctx.empresa.nome,
        tipo_destino=dados.get("destinationType", "mercado_interno"),
        caixas=dados.get("boxes"), peso_kg=dados.get("weightKg"),
        temp_min_c=faixa[0], temp_max_c=faixa[1], umidade_min_pct=fruta.umidade_min_pct,
        umidade_max_pct=fruta.umidade_max_pct, preparado_em=data,
        responsavel_empresa_id=ctx.empresa.id, responsavel_nome=ctx.empresa.nome,
        fluxo_versao=configuracao["version"], ambiente_id=ambiente.id,
    )
    sessao.add(lote)
    sessao.flush()
    nova_permanencia(sessao, lote, data)
    registrar_evento(sessao, ctx, lote, "Preparação iniciada", data, motivo=motivo, dados={
        "ambiente": ambiente.nome, "faixa": faixa, "fluxoVersao": lote.fluxo_versao,
    })
    return lote


def editar_lote(sessao, ctx, lote, dados):
    dono(ctx, lote)
    exigir_acao_fluxo(obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao), ctx.papel, "editar")
    conferir_versao(lote, dados.pop("version", None))
    if lote.fase == 3:
        erro(409, "O lote já foi recebido.")
    campos = {
        "variety": "variedade", "client": "cliente", "destination": "destino",
        "boxes": "caixas", "weightKg": "peso_kg", "origin": "origem", "producer": "produtor",
        "destinationType": "tipo_destino",
    }
    alteracoes = {}
    for campo, atributo in campos.items():
        if campo in dados and getattr(lote, atributo) != dados[campo]:
            alteracoes[campo] = {"anterior": getattr(lote, atributo), "atual": dados[campo]}
            setattr(lote, atributo, dados[campo])
    if dados.get("range"):
        if not dados.get("reason"):
            erro(422, "Justifique a correção de faixa do lote.")
        alteracoes["range"] = {"anterior": [lote.temp_min_c, lote.temp_max_c], "atual": dados["range"]}
        lote.temp_min_c, lote.temp_max_c = dados["range"]
    if alteracoes:
        lote.versao += 1
        registrar_evento(sessao, ctx, lote, "Dados do lote atualizados", agora_utc(), lote.fase,
                         dados.get("reason"), alteracoes)
    return lote


def preparar(sessao, ctx, lote, dados):
    dono(ctx, lote)
    exigir_acao_fluxo(obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao), ctx.papel, "preparar")
    conferir_versao(lote, dados.get("version"))
    if lote.fase != 0:
        erro(409, "A preparação exige um lote nessa fase.")
    ambiente = ambiente_da_empresa(sessao, ctx, dados.get("environmentId"), "camara")
    if lote.ambiente_id == ambiente.id:
        return lote
    data = efetivo(dados.get("effectiveAt"))
    encerrar_permanencia(sessao, lote, data)
    lote.ambiente_id = ambiente.id
    lote.versao += 1
    nova_permanencia(sessao, lote, data)
    registrar_evento(sessao, ctx, lote, "Ambiente de preparação alterado", data, 0,
                     dados.get("reason"), {"ambiente": ambiente.nome})
    return lote


def atribuir_responsavel(sessao, ctx, lote, id_empresa, fluxo, evento, automatica=False):
    if id_empresa is None or id_empresa == lote.responsavel_empresa_id:
        return
    if automatica:
        erro(422, "A saída detectada exige validação para atribuir responsabilidade.")
    if ctx.empresa.id not in {lote.empresa_id, lote.responsavel_empresa_id, id_empresa}:
        erro(403, "A atribuição exige participação da empresa na transferência.")
    empresa = empresa_ativa(sessao, id_empresa)
    if empresa.id != lote.empresa_id:
        comp = sessao.scalar(select(CompartilhamentoLote).where(
            CompartilhamentoLote.lote_id == lote.id, CompartilhamentoLote.empresa_id == empresa.id,
            *comp_ativo(agora_utc()),
        ))
        direito = "receber" if evento == "recebimento" else "operar"
        if comp is None or direito not in comp.direitos:
            erro(422, "A empresa indicada precisa aceitar a concessão correspondente para este lote.")
    if evento in {"carregamento", "despacho", "recebimento"} and fluxo["transferAt"] != evento:
        erro(409, "A versão de fluxo do lote prevê a transferência em outra etapa.")
    if fluxo["requireAcceptance"] and ctx.empresa.id != empresa.id and evento != "retorno":
        lote.transferencia_pendente_id = empresa.id
    else:
        lote.responsavel_empresa_id = empresa.id
        lote.responsavel_nome = empresa.nome
        lote.transferencia_pendente_id = None


def carregar_em_viagem(sessao, ctx, lote, dados, data):
    dono(ctx, lote)
    ambiente = ambiente_da_empresa(sessao, ctx, dados.get("environmentId"), "compartimento")
    viagem = sessao.scalar(select(Viagem).where(
        Viagem.codigo == dados.get("tripId"), Viagem.empresa_id == ctx.empresa.id,
    ))
    if viagem is None:
        erro(404, "Viagem indisponível.")
    if data < viagem.criado_em:
        erro(409, "O carregamento não pode anteceder o início da viagem.")
    if sessao.scalar(select(LoteOperacional.id).where(
        LoteOperacional.viagem_id == viagem.id, LoteOperacional.fase >= 2,
    ).limit(1)):
        erro(409, "A viagem já foi despachada.")
    parada_id = dados.get("stopId")
    if parada_id is not None:
        parada = sessao.get(Parada, parada_id)
        if parada is None or parada.viagem_id != viagem.id:
            erro(404, "Parada indisponível.")
    # A versão da viagem protege a associação contra despacho concorrente.
    viagem.versao += 1
    lote.ambiente_id = ambiente.id
    lote.viagem_id = viagem.id
    lote.parada_id = parada_id
    lote.carregado_em = data
    return {"ambiente": ambiente.nome, "viagem": viagem.codigo}


def mover(sessao, ctx, lote, acao, dados, automatica=False, atualizar_viagem=True):
    conferir_versao(lote, dados.get("version"))
    fluxo = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)
    exigir_acao_fluxo(fluxo, "automacao" if automatica else ctx.papel, acao)
    fase_anterior, fase_atual = TRANSICOES[acao]
    if lote.fase != fase_anterior:
        erro(409, "A fase atual não permite essa movimentação.")
    if lote.pendente and acao == "receber":
        erro(409, "Valide o despacho antes do recebimento.")
    if lote.transferencia_pendente_id:
        erro(409, "Confirme a transferência de responsabilidade pendente.")
    data = efetivo(dados.get("effectiveAt"))
    encerrar_permanencia(sessao, lote, data)
    detalhes = {"responsavelAnterior": lote.responsavel_nome}
    etapa = {"carregar": "carregamento", "despachar": "despacho", "receber": "recebimento"}[acao]
    empresa = dados.get("responsibleCompanyId")
    if acao == "receber" and empresa is None and fluxo["transferAt"] == "recebimento":
        empresa = ctx.empresa.id
    atribuir_responsavel(sessao, ctx, lote, empresa, fluxo, etapa, automatica)
    if acao == "carregar":
        detalhes.update(carregar_em_viagem(sessao, ctx, lote, dados, data))
    elif acao == "despachar":
        lote.despachado_em = data
        lote.pendente = automatica
    elif acao == "receber":
        lote.recebido_em = data
        lote.ambiente_id = None
    if atualizar_viagem and lote.viagem_id and acao in {"despachar", "receber"}:
        sessao.get(Viagem, lote.viagem_id).versao += 1
    lote.fase = fase_atual
    lote.versao += 1
    if lote.fase < 3:
        nova_permanencia(sessao, lote, data)
    detalhes.update({"responsavel": lote.responsavel_nome,
                     "transferenciaPendenteId": lote.transferencia_pendente_id})
    detalhes.update(dados.get("evidence", {}))
    tipos = {"carregar": "Carregamento registrado", "despachar": "Despacho confirmado",
             "receber": "Recebimento registrado"}
    registrar_evento(sessao, ctx, lote, "Despacho provisório" if automatica else tipos[acao],
                     data, fase_anterior, dados.get("reason"), detalhes, automatica=automatica)
    return lote


def retornar(sessao, ctx, lote, dados):
    dono(ctx, lote)
    configuracao = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)
    exigir_acao_fluxo(configuracao, ctx.papel, "retornar")
    conferir_versao(lote, dados.get("version"))
    if lote.fase <= 0:
        erro(409, "O lote já está na preparação.")
    if not dados.get("reason"):
        erro(422, "Informe a justificativa do retorno.")
    anterior = lote.fase
    data = efetivo(dados.get("effectiveAt"))
    encerrar_permanencia(sessao, lote, data)
    permanencia_anterior = sessao.scalar(select(Permanencia).where(
        Permanencia.lote_id == lote.id, Permanencia.fase == anterior - 1,
    ).order_by(Permanencia.id.desc()).limit(1))
    responsavel = dados.get("responsibleCompanyId") or (
        permanencia_anterior.responsavel_empresa_id if permanencia_anterior else lote.empresa_id
    )
    atribuir_responsavel(sessao, ctx, lote, responsavel, configuracao, "retorno")
    lote.transferencia_pendente_id = None
    lote.pendente = False
    lote.fase -= 1
    lote.versao += 1
    lote.recebido_em = None
    if lote.viagem_id:
        viagem = sessao.get(Viagem, lote.viagem_id)
        viagem.versao += 1
    if lote.fase < 2:
        lote.despachado_em = None
    if lote.fase == 0:
        ambiente = ambiente_da_empresa(sessao, ctx, dados.get("environmentId"), "camara")
        lote.ambiente_id = ambiente.id
        lote.carregado_em = None
        lote.viagem_id = None
        lote.parada_id = None
    elif permanencia_anterior:
        lote.ambiente_id = permanencia_anterior.ambiente_id
    nova_permanencia(sessao, lote, data)
    registrar_evento(sessao, ctx, lote, "Retorno de fase", data, anterior, dados["reason"], {
        "responsavel": lote.responsavel_nome,
    })
    return lote


def validar_despacho(sessao, ctx, lote, dados):
    conferir_versao(lote, dados.get("version"))
    configuracao = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)
    exigir_acao_fluxo(configuracao, ctx.papel, "validar-despacho")
    if lote.fase != 2 or not lote.pendente:
        erro(409, "Este lote não tem despacho provisório pendente.")
    if not dados.get("reason"):
        erro(422, "Informe a justificativa da validação.")
    data = efetivo(dados.get("effectiveAt")) if dados.get("effectiveAt") else lote.despachado_em
    trechos = permanencias(sessao, lote)
    if len(trechos) < 2:
        erro(409, "Não há histórico suficiente para corrigir a saída.")
    espera, transito = trechos[-2:]
    if espera.fase != 1 or transito.fase != 2 or data < espera.inicio:
        erro(409, "O horário da saída conflita com as etapas registradas.")
    anterior = lote.despachado_em
    espera.fim = data
    transito.inicio = data
    lote.despachado_em = data
    lote.pendente = False
    lote.versao += 1
    atribuir_responsavel(sessao, ctx, lote, dados.get("responsibleCompanyId"), configuracao, "despacho")
    transito.responsavel_empresa_id = lote.responsavel_empresa_id
    transito.responsavel_nome = lote.responsavel_nome
    registrar_evento(sessao, ctx, lote, "Despacho validado", data, 2, dados["reason"], {
        "efetivoAnterior": utc(anterior), "responsavel": lote.responsavel_nome,
    })
    return lote


def confirmar_transferencia(sessao, ctx, lote, dados):
    conferir_versao(lote, dados.get("version"))
    exigir_acao_fluxo(obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao), ctx.papel, "confirmar-transferencia")
    if lote.transferencia_pendente_id != ctx.empresa.id:
        erro(403, "A confirmação cabe à empresa indicada para assumir a carga.")
    data = efetivo(dados.get("effectiveAt"))
    encerrar_permanencia(sessao, lote, data)
    lote.responsavel_empresa_id = ctx.empresa.id
    lote.responsavel_nome = ctx.empresa.nome
    lote.transferencia_pendente_id = None
    lote.versao += 1
    if lote.fase < 3:
        nova_permanencia(sessao, lote, data)
    registrar_evento(sessao, ctx, lote, "Transferência confirmada", data, lote.fase, dados.get("reason"))
    return lote


def acoes_lote(sessao, ctx, lote, comp):
    globais = ctx.permissoes
    direitos = set(comp.direitos) if comp else {"operar", "receber", "rota", "laudo", "etiquetas"}
    permissoes = {"consultar"}
    permissoes.update(direitos & {"rota", "laudo"})
    if "operar" in globais and "operar" in direitos:
        if not comp:
            if lote.fase < 3:
                permissoes.add("editar")
            if lote.fase > 0:
                permissoes.add("retornar")
            else:
                permissoes.update({"preparar", "carregar"})
        if lote.fase == 1 and not lote.transferencia_pendente_id:
            permissoes.add("despachar")
        if lote.fase == 2 and lote.pendente:
            permissoes.add("validar-despacho")
    recebe = "receber" in globais or (ctx.papel == "cliente" and "consultar" in globais)
    if recebe and "receber" in direitos and lote.fase == 2 and not (lote.pendente or lote.transferencia_pendente_id):
        permissoes.add("receber")
    if not comp:
        permissoes.update(globais & {"compartilhar", "etiquetas"})
    if lote.transferencia_pendente_id == ctx.empresa.id and ("operar" in globais or (recebe and "receber" in direitos)):
        permissoes.add("confirmar-transferencia")
    configuracao = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)
    return sorted(acao for acao in permissoes if papel_permitido(configuracao, ctx.papel, acao))


def eventos_lote(sessao, lote, comp=None, offset=0, limit=100):
    consulta = select(EventoLote).where(EventoLote.lote_id == lote.id)
    if comp:
        consulta = consulta.where(EventoLote.tipo.in_(EVENTOS_COMPARTILHADOS))
        if comp.inicio_dados:
            consulta = consulta.where(EventoLote.efetivo_em >= comp.inicio_dados)
        if comp.fim_dados:
            consulta = consulta.where(EventoLote.efetivo_em < comp.fim_dados)
    total = sessao.scalar(select(func.count()).select_from(consulta.subquery()))
    eventos = sessao.scalars(consulta.order_by(EventoLote.id.desc()).offset(offset).limit(limit))
    items = [{
        "id": e.id, "tipo": e.tipo, "autor": e.autor_nome, "empresa": e.empresa_nome,
        "efetivo_em": utc(e.efetivo_em), "registrado_em": utc(e.registrado_em),
        "fase_anterior": e.fase_anterior, "fase_atual": e.fase_atual, "motivo": e.motivo,
        "dados": e.dados if not comp else {k: v for k, v in e.dados.items() if k == "responsavel"},
    } for e in eventos]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def dados_compartilhamento(sessao, comp, enviado=False):
    lote = sessao.get(LoteOperacional, comp.lote_id)
    agora = agora_utc()
    status = "pendente"
    if comp.revogado_em:
        status = "revogado"
    elif comp.expira_em <= agora:
        status = "expirado"
    elif comp.aceito_em:
        status = "aceito"
    empresa_id = comp.empresa_id if enviado else lote.empresa_id
    empresa = sessao.get(Empresa, empresa_id)
    return {"id": comp.id, "lotId": lote.codigo, "companyId": empresa_id, "company": empresa.nome,
            "rights": comp.direitos, "status": status, "expiresAt": utc(comp.expira_em),
            "from": utc(comp.inicio_dados), "to": utc(comp.fim_dados), "acceptedAt": utc(comp.aceito_em)}


def compartilhar(sessao, ctx, lote, dados):
    dono(ctx, lote)
    empresa = empresa_ativa(sessao, dados["companyId"])
    if empresa.id == lote.empresa_id:
        erro(422, "Selecione outra empresa.")
    agora = agora_utc()
    expira = instante(dados["expiresAt"]) if dados.get("expiresAt") else agora + timedelta(days=30)
    inicio = instante(dados["from"]) if dados.get("from") else None
    fim = instante(dados["to"]) if dados.get("to") else None
    if expira <= agora or (inicio and fim and fim <= inicio):
        erro(422, "Confira a validade e o intervalo da concessão.")
    comp = sessao.scalar(select(CompartilhamentoLote).where(
        CompartilhamentoLote.lote_id == lote.id, CompartilhamentoLote.empresa_id == empresa.id,
    ))
    if comp is None:
        comp = CompartilhamentoLote(lote_id=lote.id, empresa_id=empresa.id)
        sessao.add(comp)
    comp.direitos = sorted({"consultar", *dados["rights"]})
    comp.criado_em = agora
    comp.expira_em = expira
    comp.inicio_dados = inicio
    comp.fim_dados = fim
    comp.aceito_em = None
    comp.revogado_em = None
    lote.versao += 1
    registrar_evento(sessao, ctx, lote, "Compartilhamento convidado", agora, lote.fase,
                     dados={"empresa": empresa.nome, "direitos": comp.direitos,
                            "de": utc(inicio), "ate": utc(fim), "expiraEm": utc(expira)})
    sessao.flush()
    return dados_compartilhamento(sessao, comp, enviado=True)


def listar_compartilhamentos(sessao, ctx, lote=None):
    consulta = select(CompartilhamentoLote).order_by(CompartilhamentoLote.id.desc())
    if lote:
        dono(ctx, lote)
        consulta = consulta.where(CompartilhamentoLote.lote_id == lote.id)
    else:
        consulta = consulta.where(CompartilhamentoLote.empresa_id == ctx.empresa.id)
    return [dados_compartilhamento(sessao, comp, enviado=bool(lote)) for comp in sessao.scalars(consulta)]


def aceitar_compartilhamento(sessao, ctx, comp_id):
    comp = sessao.get(CompartilhamentoLote, comp_id)
    agora = agora_utc()
    if comp is None or comp.empresa_id != ctx.empresa.id or comp.revogado_em or comp.expira_em <= agora:
        erro(404, "Compartilhamento indisponível.")
    if not comp.aceito_em:
        comp.aceito_em = agora
        lote = sessao.get(LoteOperacional, comp.lote_id)
        lote.versao += 1
        registrar_evento(sessao, ctx, lote, "Compartilhamento aceito", agora, lote.fase,
                         dados={"direitos": comp.direitos})
    return dados_compartilhamento(sessao, comp)


def revogar_compartilhamento(sessao, ctx, lote, comp_id):
    dono(ctx, lote)
    comp = sessao.get(CompartilhamentoLote, comp_id)
    if comp is None or comp.lote_id != lote.id:
        erro(404, "Compartilhamento indisponível.")
    if not comp.revogado_em:
        agora = agora_utc()
        comp.revogado_em = agora
        lote.versao += 1
        if lote.transferencia_pendente_id == comp.empresa_id:
            lote.transferencia_pendente_id = None
        registrar_evento(sessao, ctx, lote, "Compartilhamento revogado", agora, lote.fase,
                         dados={"empresaId": comp.empresa_id})
    return dados_compartilhamento(sessao, comp, enviado=True)
