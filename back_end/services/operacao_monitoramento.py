"""Sensores, medições, conservação e laudos da operação."""

import hashlib
from datetime import timedelta
from itertools import groupby
from os import getenv
from secrets import token_urlsafe

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as inserir_postgresql
from sqlalchemy.dialects.sqlite import insert as inserir_sqlite
from sqlalchemy.exc import IntegrityError

from models.operacao import (
    Ambiente, FonteSensor, LaudoOperacional, LeituraFonte, LoteOperacional, Ocorrencia,
    Permanencia, RevisaoLaudo, Viagem, VinculoSensor,
)
from services import analise, thingspeak
from services.acessos import exigir
from services.datas import agora_utc, hora_recife, para_utc
from services.erros import ErroThingSpeak
from services.operacao import acoes_lote, eventos_lote, obter_fluxo, permanencias
from services.operacao_acesso import (
    confirmar, concessao, efetivo, erro, escopo, exigir_escopo, identificar, instante,
    lotes_visiveis, registrar_evento, utc,
)
from services.sincronizacao import FOLGA_DO_RELOGIO, MARGEM_DE_ATRASO


METODO = "graus-hora-segmentados-v1"
MAIOR_INTERVALO_ANALITICO = timedelta(hours=1)


def dentro(coluna, inicio, fim):
    return and_(coluna >= inicio, or_(fim.is_(None), coluna < fim))


def sensores_no_ambiente(sessao, ambiente_id, horario=None):
    horario = horario or agora_utc()
    return sessao.scalar(select(FonteSensor).join(VinculoSensor).where(
        VinculoSensor.ambiente_id == ambiente_id, VinculoSensor.inicio <= horario,
        or_(VinculoSensor.fim.is_(None), VinculoSensor.fim > horario),
    ).limit(1))


def dados_ambiente(sessao, ambiente, ctx):
    fonte = sensores_no_ambiente(sessao, ambiente.id)
    lotes = sessao.scalars(select(LoteOperacional.codigo).where(
        LoteOperacional.ambiente_id == ambiente.id, LoteOperacional.empresa_id == ctx.empresa.id,
        LoteOperacional.fase < 3,
    ).order_by(LoteOperacional.codigo))
    return {"id": ambiente.id, "name": ambiente.nome, "type": ambiente.tipo,
            "sensorId": fonte.id if fonte else None, "sensor": fonte.nome if fonte else None,
            "lotIds": list(lotes)}


def dados_sensor(sessao, fonte):
    agora = agora_utc()
    ambiente_id = sessao.scalar(select(VinculoSensor.ambiente_id).where(
        VinculoSensor.fonte_id == fonte.id, VinculoSensor.inicio <= agora,
        or_(VinculoSensor.fim.is_(None), VinculoSensor.fim > agora),
    ).limit(1))
    ultima = sessao.scalar(select(func.max(LeituraFonte.data_hora)).where(
        LeituraFonte.fonte_id == fonte.id, LeituraFonte.data_hora <= agora,
    ))
    return {"id": fonte.id, "name": fonte.nome, "type": fonte.tipo, "channel": fonte.canal,
            "environmentId": ambiente_id, "latestAt": utc(ultima)}


def sensor_da_empresa(sessao, ctx, sensor_id):
    exigir_escopo(ctx, "sensor", sensor_id)
    fonte = sessao.get(FonteSensor, sensor_id)
    if fonte is None or fonte.empresa_id != ctx.empresa.id:
        erro(404, "Sensor indisponível.")
    return fonte


def reservar(sessao, modelo, ids):
    if ids:
        sessao.execute(update(modelo).where(modelo.id.in_(ids)).values(versao=modelo.versao + 1))


def vincular_sensor(sessao, ctx, fonte, ambiente, data):
    _, ator = identificar(ctx)
    # Travas de escrita duram até o commit, inclusive se o sensor estiver livre.
    reservar(sessao, FonteSensor, [fonte.id])
    aberto = sessao.scalar(select(VinculoSensor).where(
        VinculoSensor.fonte_id == fonte.id, VinculoSensor.fim.is_(None),
    ).order_by(VinculoSensor.inicio.desc()).limit(1))
    ids = {aberto.ambiente_id} if aberto else set()
    if ambiente:
        ids.add(ambiente.id)
    reservar(sessao, Ambiente, sorted(ids))
    if aberto and data < aberto.inicio:
        erro(409, "O horário antecede a instalação vigente do sensor.")
    if aberto and ambiente and ambiente.id == aberto.ambiente_id:
        return
    if ambiente:
        sobreposicao = sessao.scalar(select(VinculoSensor.id).where(
            VinculoSensor.ambiente_id == ambiente.id,
            or_(VinculoSensor.fim.is_(None), VinculoSensor.fim > data),
        ).limit(1))
        ultimo_fim = sessao.scalar(select(func.max(VinculoSensor.fim)).where(VinculoSensor.fonte_id == fonte.id))
        if sobreposicao or (ultimo_fim and data < ultimo_fim):
            erro(409, "O horário se sobrepõe a uma instalação registrada.")
    if aberto:
        aberto.fim = data
        aberto.removido_por = ator
    if ambiente:
        sessao.add(VinculoSensor(ambiente_id=ambiente.id, fonte_id=fonte.id,
                                inicio=data, instalado_por=ator))


def consulta_leituras(lote, comp=None, inicio=None, fim=None, fase=None):
    consulta = select(LeituraFonte, FonteSensor.nome, Ambiente.nome, Permanencia, VinculoSensor.id).join(
        VinculoSensor, and_(VinculoSensor.fonte_id == LeituraFonte.fonte_id,
                            dentro(LeituraFonte.data_hora, VinculoSensor.inicio, VinculoSensor.fim)),
    ).join(Permanencia, and_(
        Permanencia.ambiente_id == VinculoSensor.ambiente_id,
        dentro(LeituraFonte.data_hora, Permanencia.inicio, Permanencia.fim),
    )).join(FonteSensor, FonteSensor.id == LeituraFonte.fonte_id).join(
        Ambiente, Ambiente.id == Permanencia.ambiente_id,
    ).where(Permanencia.lote_id == lote.id, LeituraFonte.data_hora <= agora_utc())
    if comp:
        inicio = max(filter(None, [inicio, comp.inicio_dados]), default=None)
        fim = min(filter(None, [fim, comp.fim_dados]), default=None)
    if inicio is not None:
        consulta = consulta.where(LeituraFonte.data_hora >= inicio)
    if fim is not None:
        consulta = consulta.where(LeituraFonte.data_hora < fim)
    if fase is not None:
        consulta = consulta.where(Permanencia.fase == fase)
    return consulta


def leitura_json(registro, quebra=False):
    leitura, fonte, ambiente, trecho, _ = registro
    return {"entry_id": leitura.entry_id, "data_hora": utc(leitura.data_hora),
            "recebida_em": utc(leitura.recebida_em), "temperatura_c": leitura.temperatura_c,
            "umidade_pct": leitura.umidade_pct, "luminosidade_lux": leitura.luminosidade_lux,
            "fonte_id": leitura.fonte_id, "fonte": fonte, "ambiente": ambiente, "fase": trecho.fase,
            "responsavel": trecho.responsavel_nome, "quebra": quebra}


def segmentos(registros):
    conjunto = []
    anterior = None
    for registro in registros:
        if anterior and ((registro[3].id, registro[4]) != (anterior[3].id, anterior[4]) or
                         registro[0].data_hora - anterior[0].data_hora > MAIOR_INTERVALO_ANALITICO):
            yield conjunto
            conjunto = []
        conjunto.append(registro)
        anterior = registro
    if conjunto:
        yield conjunto


def colecao_dados(registros):
    return [{"data_hora": r[0].data_hora, "temperatura_c": r[0].temperatura_c,
             "umidade_pct": r[0].umidade_pct, "luminosidade_lux": r[0].luminosidade_lux} for r in registros]


def dados_analise(lote, registros, trechos, inicio, fim):
    faixa = {"temp_min_c": lote.temp_min_c, "temp_max_c": lote.temp_max_c}
    amostras = colecao_dados(registros)
    resultado = analise.resumo_das_temperaturas(amostras, faixa) if amostras else analise.analise_sem_dados()
    acumulado = [0.0, 0.0]
    etapas = {}
    desvios, portas, cobertos = [], [], []
    for grupo in segmentos(registros):
        trecho = grupo[0][3]
        medidas = colecao_dados(grupo)
        acima, abaixo = analise.calcular_graus_hora(medidas, lote.temp_min_c, lote.temp_max_c)
        acumulado[0] += acima
        acumulado[1] += abaixo
        etapa = etapas.setdefault(trecho.id, {"fase": trecho.fase, "responsavel": trecho.responsavel_nome,
                                               "amostras": 0, "graus_hora_acima": 0.0, "graus_hora_abaixo": 0.0})
        etapa["amostras"] += len(grupo)
        etapa["graus_hora_acima"] += acima
        etapa["graus_hora_abaixo"] += abaixo
        desvios.extend(analise.detectar_trechos_fora_da_faixa(medidas, lote.temp_min_c, lote.temp_max_c))
        portas.extend(analise.detectar_eventos_porta(medidas))
        cobertos.append((medidas[0]["data_hora"], medidas[-1]["data_hora"]))
    lacunas = []
    limite_inferior = max(lote.preparado_em, inicio or lote.preparado_em)
    limite_superior = min(filter(None, [fim, lote.recebido_em, agora_utc()]))
    for trecho in trechos:
        cursor = max(trecho.inicio, limite_inferior)
        fim_trecho = min(trecho.fim or limite_superior, limite_superior)
        for de, ate in cobertos:
            if ate < cursor or de >= fim_trecho:
                continue
            if de > cursor:
                lacunas.append({"inicio": utc(cursor), "fim": utc(de), "fase": trecho.fase})
            cursor = max(cursor, ate)
        if cursor < fim_trecho:
            lacunas.append({"inicio": utc(cursor), "fim": utc(fim_trecho), "fase": trecho.fase})
    niveis = [analise.classificar_risco(grau) for grau in acumulado] if amostras else ["SEM_DADOS"] * 2
    nivel = analise.nivel_mais_grave(*niveis)
    recomendacao = analise.RECOMENDACOES[nivel]
    if nivel == "VERDE" and resultado["amostras_fora_faixa"]:
        recomendacao = analise.RECOMENDACAO_DESVIO_COM_RISCO_BAIXO
    for etapa in etapas.values():
        for chave in ("graus_hora_acima", "graus_hora_abaixo"):
            etapa[chave] = round(etapa[chave], 2)
    resultado.update({"metodo": METODO, "temperatura_faixa": [lote.temp_min_c, lote.temp_max_c],
                      "graus_hora_acima": round(acumulado[0], 2), "graus_hora_abaixo": round(acumulado[1], 2),
                      "nivel_acima": niveis[0], "nivel_abaixo": niveis[1], "nivel": nivel,
                      "recomendacao": recomendacao, "trechos_fora_faixa": desvios, "eventos_porta": portas,
                      "etapas": list(etapas.values()), "lacunas": lacunas})
    return jsonable_encoder(resultado, custom_encoder={type(lote.preparado_em): utc})


def leituras_lote(sessao, lote, comp=None, inicio=None, fim=None, fase=None, offset=0, limit=500):
    if inicio and fim and fim <= inicio:
        erro(422, "Informe um fim posterior ao início.")
    consulta = consulta_leituras(lote, comp, inicio, fim, fase)
    registros = list(sessao.execute(consulta.order_by(LeituraFonte.data_hora, LeituraFonte.entry_id)))
    items = []
    indice = 0
    if limit:
        for grupo in segmentos(registros):
            for local, registro in enumerate(grupo):
                if offset <= indice < offset + limit:
                    items.append(leitura_json(registro, local == 0 or not items))
                indice += 1
            if indice >= offset + limit:
                break
    if comp:
        inicio = max(filter(None, [inicio, comp.inicio_dados]), default=None)
        fim = min(filter(None, [fim, comp.fim_dados]), default=None)
    trechos = [p for p in permanencias(sessao, lote) if fase is None or p.fase == fase]
    return {"items": items, "total": len(registros), "offset": offset, "limit": limit,
            "analysis": dados_analise(lote, registros, trechos, inicio, fim)}


def peso_formatado(peso):
    if peso is None:
        return None
    return f"{peso:,.2f}".rstrip("0").rstrip(".").translate(str.maketrans(",.", ".,")) + " kg"


def dados_lote(sessao, ctx, lote, comp=None, detalhe=False):
    if comp is None:
        comp = concessao(sessao, ctx, lote)
    consulta = consulta_leituras(lote, comp)
    registro = sessao.execute(consulta.order_by(LeituraFonte.data_hora.desc(), LeituraFonte.entry_id.desc()).limit(1)).first()
    viagem = sessao.get(Viagem, lote.viagem_id) if lote.viagem_id else None
    rota_concedida = not comp or "rota" in comp.direitos
    ambiente = sessao.get(Ambiente, lote.ambiente_id) if lote.ambiente_id and not comp else None
    ultima = leitura_json(registro) if registro is not None else None

    def revela(data):
        if not data or not comp:
            return data
        if (comp.inicio_dados and data < comp.inicio_dados) or (comp.fim_dados and data >= comp.fim_dados):
            return None
        return data

    datas = [revela(data) for data in (lote.preparado_em, lote.carregado_em, lote.despachado_em, lote.recebido_em)]
    preparado, carregado, despachado, recebido = datas
    tempo_espera = None
    if carregado and (despachado or lote.fase == 1):
        fim_espera = despachado or agora_utc()
        if comp and comp.fim_dados:
            fim_espera = min(fim_espera, comp.fim_dados)
        tempo_espera = fim_espera - carregado
    fonte = sensores_no_ambiente(sessao, ambiente.id) if ambiente else None
    sensor = (f"{ambiente.nome} · {fonte.nome}" if fonte else ambiente.nome) if ambiente else None
    if sensor is None and ultima:
        sensor = f"{ultima['ambiente']} · {ultima['fonte']}"
    resultado = {
        "id": lote.codigo, "legacy": lote.legado_id is not None,
        "fruit": lote.fruta_nome, "fruitId": lote.fruta_id,
        "variety": lote.variedade, "client": lote.cliente, "destination": lote.destino,
        "destinationType": lote.tipo_destino, "producer": lote.produtor, "origin": lote.origem,
        "boxes": lote.caixas, "weight": peso_formatado(lote.peso_kg), "weightKg": lote.peso_kg,
        "phase": lote.fase, "temperature": ultima["temperatura_c"] if ultima else None,
        "range": [lote.temp_min_c, lote.temp_max_c], "sensor": sensor,
        "owner": lote.responsavel_nome, "responsibleCompanyId": lote.responsavel_empresa_id,
        "trip": viagem.codigo if viagem and rota_concedida else None,
        "tripId": viagem.codigo if viagem and rota_concedida else None,
        "stopId": lote.parada_id if rota_concedida else None, "environmentId": ambiente.id if ambiente else None,
        "pending": lote.pendente, "responsibilityPending": bool(lote.transferencia_pendente_id),
        "preparation": hora_recife(preparado).split()[0] if preparado else None,
        "loaded": hora_recife(carregado).split()[0] if carregado else None,
        "departed": hora_recife(despachado).split()[0] if despachado else None,
        "preparedAt": utc(preparado), "loadedAt": utc(carregado), "departedAt": utc(despachado),
        "receivedAt": utc(recebido), "latestAt": ultima["data_hora"] if ultima else None,
        "waitMinutes": max(0, int(tempo_espera.total_seconds() / 60)) if tempo_espera is not None else None,
        "version": lote.versao, "flowVersion": lote.fluxo_versao,
        "publicCode": lote.codigo_publico,
        "permissions": acoes_lote(sessao, ctx, lote, comp), "analysis": None,
    }
    if detalhe:
        resultado["analysis"] = leituras_lote(sessao, lote, comp, limit=0)["analysis"]
    return resultado


def ingerir_leitura(sessao, fonte, dados, limite):
    data = para_utc(dados["data_hora"])
    temperatura = dados["temperatura_c"]
    if dados["entry_id"] <= 0 or not analise.temperatura_valida(temperatura) or data > limite:
        return "descartada"
    if sessao.get(LeituraFonte, (fonte.id, dados["entry_id"])):
        return "repetida"
    try:
        with sessao.begin_nested():
            sessao.add(LeituraFonte(
                fonte_id=fonte.id, entry_id=dados["entry_id"], data_hora=data, recebida_em=agora_utc(),
                temperatura_c=temperatura, umidade_pct=analise.valor_na_faixa_ou_nulo(
                    dados.get("umidade_pct"), analise.UMIDADE_MIN, analise.UMIDADE_MAX),
                luminosidade_lux=analise.valor_na_faixa_ou_nulo(dados.get("luminosidade_lux"), analise.LUX_MIN, analise.LUX_MAX),
            ))
    except IntegrityError:
        if sessao.get(LeituraFonte, (fonte.id, dados["entry_id"])) is None:
            raise
        return "repetida"
    return "nova"


def sincronizar(sessao, ctx, sensor_id=None, desde=None):
    exigir(ctx, "integrar" if ctx.integracao or "operar" not in ctx.permissoes else "operar")
    consulta = select(FonteSensor).where(FonteSensor.empresa_id == ctx.empresa.id, FonteSensor.tipo == "thingspeak")
    if sensor_id:
        sensor_da_empresa(sessao, ctx, sensor_id)
        consulta = consulta.where(FonteSensor.id == sensor_id)
    fontes = [fonte for fonte in sessao.scalars(consulta) if escopo(ctx, "sensor", fonte.id)]
    canais, falhas = [], []
    for fonte in fontes:
        limite = agora_utc() + FOLGA_DO_RELOGIO
        ultima = sessao.scalar(select(func.max(LeituraFonte.data_hora)).where(
            LeituraFonte.fonte_id == fonte.id, LeituraFonte.data_hora <= limite,
        ))
        inicio = desde if desde is not None else (ultima - MARGEM_DE_ATRASO if ultima else None)
        chave = getenv(f"PLANTSYNC_THINGSPEAK_CHAVE_{fonte.empresa_id}_{fonte.canal}")
        try:
            recebidas = thingspeak.buscar_leituras(fonte.canal, desde=inicio, chave_leitura=chave)
        except ErroThingSpeak:
            falhas.append({"sensorId": fonte.id, "mensagem": "Não foi possível ler o canal do sensor."})
            continue
        contagem = {"nova": 0, "descartada": 0, "repetida": 0}
        reservar(sessao, FonteSensor, [fonte.id])
        for leitura in recebidas:
            contagem[ingerir_leitura(sessao, fonte, leitura, limite)] += 1
        canais.append({"sensorId": fonte.id, "recebidas": len(recebidas),
                       "novas": contagem["nova"], "descartadas": contagem["descartada"]})
        confirmar(sessao)
    if fontes and not canais:
        erro(503, "Não foi possível sincronizar os sensores selecionados.")
    gerar_ocorrencias(sessao, ctx.empresa.id)
    return {"novas": sum(c["novas"] for c in canais), "recebidas": sum(c["recebidas"] for c in canais),
            "descartadas": sum(c["descartadas"] for c in canais), "canais": canais, "falhas": falhas}


def ocorrencia(sessao, lote, chave, tipo, inicio, detalhe, fonte_id=None, fim=None, responsavel_id=None):
    inserir = {"sqlite": inserir_sqlite, "postgresql": inserir_postgresql}[sessao.bind.dialect.name]
    comando = inserir(Ocorrencia).values(
        lote_id=lote.id, tipo=tipo, deduplicacao=chave, fonte_id=fonte_id,
        responsavel_empresa_id=responsavel_id or lote.responsavel_empresa_id,
        inicio=inicio, fim=fim, detalhe=detalhe, estado="aberta", versao=1,
    ).on_conflict_do_nothing(index_elements=[Ocorrencia.deduplicacao])
    sessao.execute(comando)
    registro = sessao.scalar(select(Ocorrencia).where(Ocorrencia.deduplicacao == chave))
    if fim and (registro.fim is None or fim > registro.fim):
        registro.fim = fim
    if inicio < registro.inicio:
        registro.inicio = inicio
    return registro


def gerar_ocorrencias(sessao, empresa_id, lote_id=None):
    consulta = select(LoteOperacional).where(LoteOperacional.empresa_id == empresa_id, LoteOperacional.fase < 3)
    if lote_id:
        consulta = consulta.where(LoteOperacional.id == lote_id)
    agora = agora_utc()
    for lote in sessao.scalars(consulta):
        registros = list(sessao.execute(consulta_leituras(lote).order_by(LeituraFonte.data_hora, LeituraFonte.entry_id)))
        for (trecho_id, vinculo_id), grupo in groupby(registros, lambda r: (r[3].id, r[4])):
            medidas = list(grupo)
            for lado, selecionadas in (
                ("acima", [r for r in medidas if r[0].temperatura_c > lote.temp_max_c]),
                ("abaixo", [r for r in medidas if r[0].temperatura_c < lote.temp_min_c]),
            ):
                if selecionadas:
                    primeira, ultima = selecionadas[0], selecionadas[-1]
                    ocorrencia(sessao, lote, f"desvio:{lote.id}:{trecho_id}:{vinculo_id}:{lado}", "conservacao",
                               primeira[0].data_hora, f"Temperatura {lado} da faixa do lote.",
                               primeira[0].fonte_id, ultima[0].data_hora, primeira[3].responsavel_empresa_id)
        minutos = obter_fluxo(sessao, lote.empresa_id, lote.fluxo_versao)["absenceMinutes"]
        if minutos:
            trechos = permanencias(sessao, lote)
            atual = trechos[-1] if trechos else None
            ultima_leitura = registros[-1][0] if registros else None
            desde = max(atual.inicio if atual else lote.preparado_em,
                        ultima_leitura.data_hora if ultima_leitura else lote.preparado_em)
            if agora - desde >= timedelta(minutes=minutos):
                ocorrencia(sessao, lote, f"ausencia:{lote.id}:{utc(desde)}", "ausencia", desde,
                           "Intervalo sem novas medições acima do limite configurado.",
                           ultima_leitura.fonte_id if ultima_leitura else None, agora)


def dados_alerta(sessao, ocorrencia):
    lote = sessao.get(LoteOperacional, ocorrencia.lote_id)
    return {"id": ocorrencia.id, "lotId": lote.codigo, "type": ocorrencia.tipo, "status": ocorrencia.estado,
            "message": ocorrencia.detalhe, "startedAt": utc(ocorrencia.inicio), "endedAt": utc(ocorrencia.fim),
            "sourceId": ocorrencia.fonte_id, "responsibleCompanyId": ocorrencia.responsavel_empresa_id,
            "version": ocorrencia.versao}


def listar_alertas(sessao, ctx, offset, limit):
    exigir(ctx, "consultar")
    lotes = {l.id: concessao(sessao, ctx, l) for l in lotes_visiveis(sessao, ctx)}
    consulta = select(Ocorrencia).where(Ocorrencia.lote_id.in_(lotes)).order_by(Ocorrencia.inicio.desc(), Ocorrencia.id.desc())
    alertas = []
    for registro in sessao.scalars(consulta):
        comp = lotes[registro.lote_id]
        if not alerta_visivel(registro, comp):
            continue
        alertas.append(dados_alerta(sessao, registro))
    return alertas[offset:offset + limit]


def alerta_visivel(registro, comp):
    return not comp or (
        (not comp.inicio_dados or registro.inicio >= comp.inicio_dados) and
        (not comp.fim_dados or (registro.fim or registro.inicio) < comp.fim_dados) and
        registro.tipo != "saida"
    )


def resumo_publico(sessao, codigo):
    lote = sessao.scalar(select(LoteOperacional).where(LoteOperacional.codigo_publico == codigo))
    if lote is None:
        erro(404, "Código público indisponível.")
    selo = {"elegivel": False, "motivo": "Critérios de avaliação do selo em validação."}
    return {"id": lote.codigo, "fruit": lote.fruta_nome, "producer": lote.produtor, "origin": lote.origem,
            "seal": selo, "fruta": lote.fruta_nome, "produtor": lote.produtor, "origem": lote.origem,
            "selo": selo, "selo_faixa_segura": False}


def laudo(sessao, lote, comp=None):
    if comp and "laudo" not in comp.direitos:
        erro(403, "A concessão não inclui acesso ao laudo.")
    dados = leituras_lote(sessao, lote, comp, limit=1000)
    historico = eventos_lote(sessao, lote, comp, limit=500)
    return {**resumo_publico(sessao, lote.codigo_publico), "range": [lote.temp_min_c, lote.temp_max_c],
            "analysis": dados["analysis"], "readings": dados["items"], "readingCount": dados["total"],
            "events": historico["items"], "eventCount": historico["total"], "version": lote.versao,
            "analise": dados["analysis"], "leituras": dados["items"],
            "faixa": {"temp_min_c": lote.temp_min_c, "temp_max_c": lote.temp_max_c}}


def dados_revisao(revisao):
    return {"id": revisao.id, "issuedAt": utc(revisao.emitido_em), "reason": revisao.motivo,
            "version": revisao.documento["version"], "readingCount": revisao.documento["readingCount"]}


def revisoes_laudo(sessao, lote, offset=0, limit=100):
    consulta = select(RevisaoLaudo).where(RevisaoLaudo.lote_id == lote.id)
    consulta = consulta.order_by(RevisaoLaudo.id.desc()).offset(offset).limit(limit)
    return [dados_revisao(revisao) for revisao in sessao.scalars(consulta)]


def consultar_revisao_laudo(sessao, lote, revisao_id):
    revisao = sessao.get(RevisaoLaudo, revisao_id)
    if revisao is None or revisao.lote_id != lote.id:
        erro(404, "Revisão indisponível.")
    return {**revisao.documento, "revision": dados_revisao(revisao)}


def laudo_secreto(sessao, token):
    registro = sessao.scalar(select(LaudoOperacional).where(
        LaudoOperacional.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        LaudoOperacional.revogado_em.is_(None),
        or_(LaudoOperacional.expira_em.is_(None), LaudoOperacional.expira_em > agora_utc()),
    ))
    if registro is None:
        erro(404, "Laudo indisponível.")
    revisao = sessao.scalar(select(RevisaoLaudo).where(RevisaoLaudo.laudo_id == registro.id))
    if revisao:
        return {**revisao.documento, "revision": dados_revisao(revisao)}
    return laudo(sessao, sessao.get(LoteOperacional, registro.lote_id))


def revogar_laudos(sessao, ctx, lote):
    agora = agora_utc()
    sessao.execute(update(LaudoOperacional).where(
        LaudoOperacional.lote_id == lote.id, LaudoOperacional.revogado_em.is_(None),
    ).values(revogado_em=agora))
    lote.versao += 1
    registrar_evento(sessao, ctx, lote, "Acesso por link ao laudo revogado", agora, lote.fase)


def emitir_laudo(sessao, ctx, lote, expira_em, motivo=None):
    agora = agora_utc()
    expira = instante(expira_em) if expira_em else agora + timedelta(days=7)
    if expira <= agora or expira > agora + timedelta(days=90):
        erro(422, "Informe uma validade futura de até 90 dias.")
    revogar_laudos(sessao, ctx, lote)
    token = token_urlsafe(32)
    link = LaudoOperacional(lote_id=lote.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                            criado_em=agora, expira_em=expira)
    sessao.add(link)
    registrar_evento(sessao, ctx, lote, "Acesso por link ao laudo emitido", agora, lote.fase)
    sessao.flush()
    revisao = RevisaoLaudo(lote_id=lote.id, laudo_id=link.id, autor_id=ctx.conta.id, emitido_em=agora,
                          motivo=motivo or "Emissão de laudo", documento=laudo(sessao, lote))
    sessao.add(revisao)
    sessao.flush()
    return {"token": token, "expiresAt": utc(expira), "path": f"/api/v1/laudos/{token}",
            "revision": dados_revisao(revisao)}
