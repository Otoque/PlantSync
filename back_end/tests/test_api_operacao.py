"""Fluxos operacionais com sessões reais, empresas separadas e dados descartáveis."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from controllers import catalogo, operacao as rotas_operacionais
from models.banco import abrir_sessao
from models.contas import Conta, Empresa, Integracao, PermissoesPapel, SessaoConta, VinculoConta
from services import operacao_viagens
from services.autenticacao import hash_do_token


def utc_depois(instante, segundos):
    return (datetime.fromisoformat(instante) + timedelta(seconds=segundos)).isoformat()


@pytest.fixture
def operacao(banco):
    api = FastAPI()
    api.include_router(catalogo.router)
    api.include_router(rotas_operacionais.router)

    def banco_teste():
        with banco() as sessao:
            yield sessao

    api.dependency_overrides[abrir_sessao] = banco_teste
    fim = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)
    with banco() as sessao:
        for numero, nome, papel in [(1, "Origem", "administrador"), (2, "Destino", "cliente"),
                                    (3, "Terceira", "administrador")]:
            sessao.add_all([Empresa(id=numero, nome=nome), Conta(id=numero, nome=nome, sal="x", senha_hash="x")])
            sessao.flush()
            sessao.add(VinculoConta(empresa_id=numero, conta_id=numero, papel=papel))
            sessao.add(SessaoConta(token_hash=hash_do_token(f"pss_teste{numero}"), conta_id=numero, expira_em=fim))
        sessao.add(Integracao(empresa_id=1, nome="GPS", token_hash=hash_do_token("psi_teste"),
                              expira_em=fim, permissoes=["integrar"], recurso_tipo="viagem", recurso_id="V-1"))
        sessao.add(Conta(id=4, nome="Gestor", sal="x", senha_hash="x"))
        sessao.flush()
        sessao.add(VinculoConta(empresa_id=1, conta_id=4, papel="gestor"))
        sessao.add(SessaoConta(token_hash=hash_do_token("pss_teste4"), conta_id=4, expira_em=fim))
        sessao.commit()
    with TestClient(api, base_url="http://testserver/api/v1/") as cliente:
        yield cliente


def headers(empresa=1, chave=None, integracao=False):
    retorno = {"Authorization": "Bearer psi_teste" if integracao else f"Bearer pss_teste{empresa}",
               "X-Empresa-ID": str(empresa)}
    if chave:
        retorno["Idempotency-Key"] = chave
    return retorno


def post(cliente, rota, dados=None, empresa=1, codigo=200, chave=None, integracao=False):
    resposta = cliente.post(rota, json=dados, headers=headers(empresa, chave, integracao))
    assert resposta.status_code == codigo, resposta.text
    return resposta.json()


def obter(cliente, rota, empresa=1, codigo=200, integracao=False):
    resposta = cliente.get(rota, headers=headers(empresa, integracao=integracao))
    assert resposta.status_code == codigo, resposta.text
    return resposta.json()


def criar_cenario(cliente, segundo=False):
    passado = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    dia = utc_depois(passado, 30)
    camara = post(cliente, "ambientes", {"name": "Câmara", "type": "camara"}, codigo=201)["id"]
    compartimento = post(cliente, "ambientes", {"name": "Baú", "type": "compartimento"}, codigo=201)["id"]
    fonte = post(cliente, "sensores", {"name": "Sensor A", "type": "manual", "environmentId": camara,
                                    "effectiveAt": passado}, codigo=201)["id"]
    viagem = post(cliente, "viagens", {"id": "V-1", "vehicle": "Veículo", "carrier": "Transportadora",
                                      "responsible": "Operador", "createdAt": passado,
                                      "stops": [{"name": "Primeira"}, {"name": "Segunda"}]}, codigo=201)
    fruta_id = obter(cliente, "frutas")[0]["id"]
    lotes = []
    for i in range(2 if segundo else 1):
        lotes.append(post(cliente, "lotes", {"id": f"PS-{i + 1:04}", "fruitId": fruta_id, "client": "Comprador",
                                            "destination": "Destino", "environmentId": camara, "preparedAt": dia},
                          codigo=201))
    return lotes, viagem, fonte, compartimento, passado


def carregar(cliente, lote, viagem, compartimento, horario, parada=0):
    return post(cliente, f"lotes/{lote['id']}/carregar", {"version": lote["version"],
                 "tripId": viagem["id"], "stopId": viagem["stops"][parada]["id"],
                 "environmentId": compartimento, "effectiveAt": horario})


def compartilhar(cliente, lote, direitos, aceitar=True):
    convite = post(cliente, f"lotes/{lote['id']}/compartilhamentos", {"companyId": 2, "rights": direitos}, codigo=201)
    obter(cliente, f"lotes/{lote['id']}", empresa=2, codigo=404)
    if aceitar:
        post(cliente, f"compartilhamentos/{convite['id']}/aceitar", empresa=2)
    return convite


def test_movimentos_concessoes_e_rotas_sao_isolados(operacao):
    (primeiro, segundo), viagem, _, compartimento, passado = criar_cenario(operacao, segundo=True)
    primeiro = carregar(operacao, primeiro, viagem, compartimento, utc_depois(passado, 60))
    segundo = carregar(operacao, segundo, viagem, compartimento, utc_depois(passado, 70), parada=1)
    post(operacao, "viagens/V-1/despachar", {"effectiveAt": utc_depois(passado, 80)}, chave="despacho")
    repeticao = post(operacao, "viagens/V-1/despachar", {"effectiveAt": utc_depois(passado, 80)}, chave="despacho")
    assert repeticao["dispatched"] == [primeiro["id"], segundo["id"]]
    post(operacao, "viagens/V-1/despachar", {"effectiveAt": utc_depois(passado, 81)}, chave="despacho", codigo=409)
    convite = compartilhar(operacao, primeiro, ["consultar", "receber", "rota"])
    compartilhar(operacao, segundo, ["consultar"])
    recebido = obter(operacao, "lotes/1", empresa=2)
    assert "receber" in recebido["permissions"]
    assert obter(operacao, "viagens/V-1", empresa=2)["lotIds"] == [primeiro["id"]]
    assert [p["name"] for p in obter(operacao, "viagens/V-1", empresa=2)["stops"]] == ["Primeira"]
    obter(operacao, "lotes/1/laudo", empresa=2, codigo=403)
    post(operacao, "lotes/2/receber", {}, empresa=2, codigo=403)
    post(operacao, "lotes/1/receber", {"version": recebido["version"], "effectiveAt": utc_depois(passado, 100)}, empresa=2)
    assert obter(operacao, "lotes/1")["phase"] == 3
    assert obter(operacao, "lotes/2")["phase"] == 2
    assert obter(operacao, "lotes/1/historico")["items"][0]["empresa"] == "Destino"
    obter(operacao, "viagens/V-1", empresa=3, codigo=404)
    resposta = operacao.delete(f"lotes/1/compartilhamentos/{convite['id']}", headers=headers())
    assert resposta.status_code == 200
    obter(operacao, "lotes/1", empresa=2, codigo=404)
    obter(operacao, "viagens/V-1", empresa=2, codigo=404)


def test_medicao_fronteiras_lacunas_e_fontes(operacao):
    (lote, outro), viagem, fonte, compartimento, passado = criar_cenario(operacao, segundo=True)
    outro_sensor = post(operacao, "sensores", {"name": "Sensor B", "type": "manual", "environmentId": compartimento,
                                             "effectiveAt": passado}, codigo=201)["id"]
    post(operacao, f"sensores/{outro_sensor}/vincular", {"environmentId": lote["environmentId"]}, codigo=409)
    carregar(operacao, lote, viagem, compartimento, utc_depois(passado, 60))
    def medir(sensor_id, entrada, segundos, temp):
        return post(operacao, f"sensores/{sensor_id}/leituras", {"entryId": entrada,
                    "measuredAt": utc_depois(passado, segundos), "temperature": temp})

    assert medir(fonte, 1, 60, 40)["status"] == "nova"
    assert medir(fonte, 2, 45, 8)["status"] == "nova"
    assert medir(outro_sensor, 1, 60, 10)["status"] == "nova"
    assert medir(outro_sensor, 1, 60, 10)["status"] == "repetida"
    assert medir(outro_sensor, 2, 90, 11)["status"] == "nova"
    medicao = obter(operacao, f"lotes/{lote['id']}/leituras?limit=2")
    assert medicao["total"] == 3
    assert [(m["fase"], m["temperatura_c"]) for m in medicao["items"]] == [(0, 8), (1, 10)]
    assert all(m["quebra"] for m in medicao["items"])
    assert medicao["analysis"]["temp_max_c"] == 11
    assert medicao["analysis"]["lacunas"]
    assert len(medicao["analysis"]["etapas"]) == 2
    assert obter(operacao, f"lotes/{outro['id']}/leituras")["analysis"]["temp_max_c"] == 40


def test_rastreio_escopo_janela_de_entrega_e_laudo(operacao):
    (lote,), viagem, _, compartimento, passado = criar_cenario(operacao)
    carregar(operacao, lote, viagem, compartimento, utc_depois(passado, 60))
    post(operacao, "viagens/V-1/despachar", {"effectiveAt": utc_depois(passado, 80)})
    compartilhar(operacao, lote, ["consultar", "rota", "receber", "laudo"])
    post(operacao, "viagens/V-2/rastreio/iniciar", {"source": "externa"}, chave="iniciar", integracao=True, codigo=404)
    post(operacao, "viagens/V-1/rastreio/iniciar", {"source": "externa"}, integracao=True, codigo=422)
    post(operacao, "viagens/V-1/rastreio/iniciar", {"source": "externa"}, chave="iniciar", integracao=True)
    def inserir(entrada, medida_em):
        return post(operacao, "viagens/V-1/posicoes", {"entryId": entrada, "latitude": -8.1,
                    "longitude": -34.9, "measuredAt": medida_em.isoformat(), "source": "externa", "accuracy": 16},
                    chave=entrada, integracao=True, codigo=201)

    posicao = datetime.now(timezone.utc)
    inserir("antes", posicao)
    post(operacao, "lotes/1/receber", {"effectiveAt": datetime.now(timezone.utc).isoformat()}, empresa=2)
    inserir("depois", datetime.now(timezone.utc))
    assert obter(operacao, "viagens/V-1/posicoes")["total"] == 2
    assert obter(operacao, "viagens/V-1/posicoes", empresa=2)["total"] == 1
    obter(operacao, "lotes/1", integracao=True, codigo=403)
    publico = obter(operacao, f"publico/{lote['publicCode']}")
    assert not {"temperature", "readings", "destination", "token", "trip"} & publico.keys()
    link = post(operacao, "lotes/1/laudo", {}, codigo=201)
    assert "analysis" in obter(operacao, f"laudos/{link['token']}")
    assert operacao.delete("lotes/1/laudo", headers=headers()).status_code == 204
    obter(operacao, f"laudos/{link['token']}", codigo=404)


def test_repetir_comando_apos_reduzir_permissoes_nao_revela_resposta_antiga(operacao, banco):
    criar_cenario(operacao)
    acesso_gestor = {"Authorization": "Bearer pss_teste4", "X-Empresa-ID": "1", "Idempotency-Key": "editar-destino"}
    dados = {"destination": "Destino restrito"}
    primeira = operacao.patch("lotes/1", json=dados, headers=acesso_gestor)
    assert primeira.status_code == 200 and primeira.json()["destination"] == "Destino restrito"
    with banco() as sessao:
        sessao.add(PermissoesPapel(empresa_id=1, papel="gestor", permissoes=["operar"]))
        sessao.commit()
    repeticao = operacao.patch("lotes/1", json=dados, headers=acesso_gestor)
    assert repeticao.status_code == 409 and "Destino restrito" not in repeticao.text
    acesso_gestor["Idempotency-Key"] = "editar-destino-novo"
    nova = operacao.patch("lotes/1", json=dados, headers=acesso_gestor)
    assert nova.status_code == 200 and "destination" not in nova.json()


def test_fluxo_versionado_saida_provisoria_e_validacao(operacao, monkeypatch):
    configuracao = operacao.patch("configuracoes/fluxo", headers=headers(), json={
        "version": 0, "automatic": True, "departureDetection": {
            "latitude": 0, "longitude": 0, "radiusMeters": 100, "maxAccuracyMeters": 20,
            "maxAgeMinutes": 5, "persistenceSeconds": 5, "autoDelaySeconds": 8,
        }, "allowedRolesByAction": {"despachar": ["administrador", "automacao"]},
    })
    assert configuracao.status_code == 200, configuracao.text
    (lote,), viagem, _, compartimento, passado = criar_cenario(operacao)
    carregar(operacao, lote, viagem, compartimento, utc_depois(passado, 60))
    mudanca = operacao.patch("configuracoes/fluxo", headers=headers(), json={"version": 1, "automatic": False})
    assert mudanca.status_code == 200, mudanca.text
    base = datetime.now(timezone.utc) - timedelta(seconds=70)
    with monkeypatch.context() as patch:
        patch.setattr(operacao_viagens, "agora_utc", lambda: base.replace(tzinfo=None))
        post(operacao, "viagens/V-1/rastreio/iniciar", {"source": "celular"})

    for entrada, segundos, latitude in [("dentro", 1, 0), ("fora-1", 2, 0.01), ("fora-2", 12, 0.01)]:
        post(operacao, "viagens/V-1/posicoes", {"entryId": entrada, "latitude": latitude, "longitude": 0,
             "measuredAt": (base + timedelta(seconds=segundos)).isoformat(), "source": "celular", "accuracy": 10},
             codigo=201)
        estado = obter(operacao, "lotes/1")
        assert estado["phase"] == (2 if entrada == "fora-2" else 1)
    assert estado["pending"] and estado["flowVersion"] == 1
    post(operacao, "lotes/1/receber", {}, codigo=409)
    corrigido = (base + timedelta(seconds=4)).isoformat()
    validado = post(operacao, "lotes/1/validar-despacho", {"reason": "Hora registrada na portaria", "effectiveAt": corrigido})
    assert not validado["pending"]
    assert datetime.fromisoformat(validado["departedAt"]) == datetime.fromisoformat(corrigido)
    historico = obter(operacao, "lotes/1/historico")["items"]
    assert [e["tipo"] for e in historico[:3]] == ["Despacho validado", "Despacho provisório", "Saída detectada"]
    assert historico[1]["autor"] == "Automação PlantSync"


def test_laudo_emitido_preserva_revisao_apos_leitura_atrasada(operacao):
    (_,), _, fonte, _, passado = criar_cenario(operacao)
    primeiro = post(operacao, "lotes/1/laudo", {}, codigo=201)
    post(operacao, f"sensores/{fonte}/leituras", {"entryId": 1, "measuredAt": utc_depois(passado, 45), "temperature": 10})
    assert obter(operacao, f"laudos/{primeiro['token']}")["readingCount"] == 0
    assert obter(operacao, "lotes/1/laudo")["hasUnissuedChanges"]
    segundo = post(operacao, "lotes/1/laudo", {"reason": "Medição tardia recebida"}, codigo=201)
    assert obter(operacao, f"laudos/{segundo['token']}")["readingCount"] == 1
    obter(operacao, f"laudos/{primeiro['token']}", codigo=404)
    assert [r["readingCount"] for r in obter(operacao, "lotes/1/laudo/revisoes")] == [1, 0]
    revisao = primeiro["revision"]["id"]
    assert obter(operacao, f"lotes/1/laudo/revisoes/{revisao}")["readingCount"] == 0
