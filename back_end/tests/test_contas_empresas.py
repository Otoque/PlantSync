"""Contratos de sessão individual, vínculo, convite e credencial de integração."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import sessionmaker

from app import app
from models.banco import Base, abrir_sessao
from models.contas import Conta, ConviteConta, EventoAcesso, Integracao, SessaoConta, TentativaLogin, VinculoConta
from services import acessos, autenticacao
from services.datas import agora_utc, formatar_utc


SENHA_INICIAL = "primeira senha de teste"
NOVA_SENHA = "senha atualizada de teste"


@pytest.fixture
def api_acessos(banco, monkeypatch):
    def abrir_banco_teste():
        with banco() as sessao:
            yield sessao

    monkeypatch.setitem(app.dependency_overrides, abrir_sessao, abrir_banco_teste)
    with banco() as sessao:
        empresa, conta = acessos.preparar_conta_inicial(sessao, "operacao", SENHA_INICIAL, "Frutas Norte")
        ids = empresa.id, conta.id
        sessao.commit()
    return TestClient(app), *ids


def login(api, usuario="operacao", senha=SENHA_INICIAL):
    resposta = api.post("/api/v1/login", json={"usuario": usuario, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["Cache-Control"] == "no-store"
    return resposta.json()


def headers(token, empresa_id=None):
    cabecalhos = {"Authorization": f"Bearer {token}"}
    if empresa_id is not None:
        cabecalhos["X-Empresa-ID"] = str(empresa_id)
    return cabecalhos


def criar_empresa(api, token, nome):
    resposta = api.post("/api/v1/empresas", headers=headers(token), json={"nome": nome})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def convidar(api, token, email, papel="gestor", empresa_id=None):
    resposta = api.post("/api/v1/equipe/convites", headers=headers(token, empresa_id),
                        json={"email": email, "papel": papel})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def aceitar(api, convite, email=None, token=None):
    return api.post("/api/v1/convites/aceitar", headers=headers(token) if token else {},
                    json={"token": convite["token"], "email": email or convite["convite"]["email"],
                          "nome": "Pessoa Teste", "senha": SENHA_INICIAL})


def test_login_expiracao_revogacao_e_senha(api_acessos, banco):
    api, empresa_id, conta_id = api_acessos
    assert api.post("/api/v1/conta/senha").status_code == 401
    dados = login(api)
    assert dados["usuario"] == {"id": conta_id, "nome": "operacao", "plataforma": True}
    assert [empresa["id"] for empresa in dados["empresas"]] == [empresa_id]
    assert api.get("/api/v1/contexto", headers=headers(dados["token"])).json()["empresa"] == dados["empresas"][0]
    hash_token = autenticacao.hash_do_token(dados["token"])
    with banco() as sessao:
        sessao_conta = sessao.get(SessaoConta, hash_token)
        assert sessao_conta.conta_id == conta_id
        assert sessao.get(SessaoConta, dados["token"]) is None
        sessao_conta.expira_em = agora_utc() - timedelta(seconds=1)
        sessao.commit()
    assert api.get("/api/v1/contexto", headers=headers(dados["token"])).status_code == 401

    token_a = login(api)["token"]
    token_b = login(api)["token"]
    assert api.post("/api/v1/logout", headers=headers(token_a)).status_code == 200
    assert api.get("/api/v1/contexto", headers=headers(token_a)).status_code == 401
    assert api.get("/api/v1/contexto", headers=headers(token_b)).status_code == 200
    token_c = login(api)["token"]
    troca = api.post("/api/v1/conta/senha", headers=headers(token_b),
                    json={"senha_atual": SENHA_INICIAL, "nova_senha": NOVA_SENHA})
    assert troca.status_code == 204, troca.text
    assert api.get("/api/v1/contexto", headers=headers(token_b)).status_code == 401
    assert api.get("/api/v1/contexto", headers=headers(token_c)).status_code == 401
    assert api.post("/api/v1/login", json={"usuario": "operacao", "senha": SENHA_INICIAL}).status_code == 401
    token_d = login(api, senha=NOVA_SENHA)["token"]
    with banco() as sessao:
        sessao.get(Conta, conta_id).ativo = False
        sessao.commit()
    assert api.get("/api/v1/contexto", headers=headers(token_d)).status_code == 401


def test_limite_persistente_e_credenciais_invalidas(api_acessos, banco, monkeypatch):
    api, _, _ = api_acessos
    monkeypatch.setattr(acessos, "LIMITE_LOGIN_USUARIO", 2)
    tentativa = {"usuario": "operacao", "senha": "incorreta"}
    erro_conhecido = api.post("/api/v1/login", json=tentativa)
    erro_desconhecido = api.post("/api/v1/login", json={**tentativa, "usuario": "outra"})
    assert erro_conhecido.status_code == erro_desconhecido.status_code == 401
    assert erro_conhecido.json() == erro_desconhecido.json()
    assert erro_conhecido.headers["WWW-Authenticate"] == "Bearer"
    assert api.post("/api/v1/login", json=tentativa).status_code == 401
    bloqueio = TestClient(app).post("/api/v1/login", json={**tentativa, "senha": SENHA_INICIAL})
    assert bloqueio.status_code == 429
    assert int(bloqueio.headers["Retry-After"]) > 0
    with banco() as sessao:
        assert list(sessao.scalars(select(TentativaLogin.quantidade).order_by(TentativaLogin.quantidade))) == [1, 2, 4]


def test_empresa_exige_vinculo_e_contexto_explicito(api_acessos, banco):
    api, empresa_a, conta_id = api_acessos
    token = login(api)["token"]
    empresa_b = criar_empresa(api, token, "Frutas Sul")
    assert api.get("/api/v1/contexto", headers=headers(token, empresa_b)).status_code == 403
    assert api.get("/api/v1/equipe", headers=headers(token, empresa_b)).status_code == 403
    with banco() as sessao:
        sessao.add(VinculoConta(empresa_id=empresa_b, conta_id=conta_id, papel="cliente"))
        sessao.commit()
    assert api.get("/api/v1/contexto", headers=headers(token)).status_code == 403
    assert api.get("/api/v1/contexto", headers=headers(token, empresa_b)).json()["empresa"]["permissoes"] == ["consultar"]
    assert api.get("/api/v1/equipe", headers=headers(token, empresa_b)).status_code == 403
    resposta = api.post("/api/v1/equipe/convites", headers=headers(token, empresa_a),
                        json={"email": "gestor@example.test", "papel": "gestor", "empresa_id": empresa_b})
    assert resposta.status_code == 400
    assert api.get("/api/v1/contexto", headers=headers(token, 2**63)).status_code == 400
    assert api.patch(f"/api/v1/empresas/{empresa_b}", headers=headers(token), json={"ativo": False}).status_code == 200
    assert api.get("/api/v1/contexto", headers=headers(token, empresa_b)).status_code == 403
    assert api.get("/api/v1/contexto", headers=headers(token)).json()["empresa"]["id"] == empresa_a


def test_convite_destinatario_uso_unico_papel_revogacao_e_auditoria(api_acessos, banco):
    api, empresa_id, admin_id = api_acessos
    admin = login(api)["token"]
    convite = convidar(api, admin, "Gestora@example.test")
    assert aceitar(api, convite, email="outro@example.test").status_code == 400
    with banco() as sessao:
        linha = sessao.get(ConviteConta, convite["convite"]["id"])
        assert linha.token_hash == autenticacao.hash_do_token(convite["token"])
    resposta = aceitar(api, convite)
    assert resposta.status_code == 201, resposta.text
    pessoa_id = resposta.json()["usuario"]["id"]
    assert aceitar(api, convite).status_code == 409
    gestor = login(api, "GESTORA@example.test")["token"]
    assert api.get("/api/v1/empresas", headers=headers(gestor)).status_code == 403
    assert "operar" in api.get("/api/v1/contexto", headers=headers(gestor)).json()["empresa"]["permissoes"]

    ultimo_admin = api.patch(f"/api/v1/equipe/{admin_id}", headers=headers(admin), json={"ativo": False})
    assert ultimo_admin.status_code == 409
    vinculo = f"/api/v1/equipe/{pessoa_id}"
    assert api.patch(vinculo, headers=headers(admin), json={"papel": "cliente"}).status_code == 200
    assert api.get("/api/v1/contexto", headers=headers(gestor)).json()["empresa"]["permissoes"] == ["consultar"]
    assert api.patch(vinculo, headers=headers(admin), json={"ativo": False}).status_code == 200
    assert api.get("/api/v1/contexto", headers=headers(gestor, empresa_id)).status_code == 403
    with banco() as sessao:
        acoes = list(sessao.scalars(select(EventoAcesso.acao).order_by(EventoAcesso.id)))
        assert acoes == ["emitir_convite", "aceitar_convite", "alterar_vinculo", "alterar_vinculo"]


def test_convites_reemitidos_expirados_e_conta_existente(api_acessos, banco):
    api, _, _ = api_acessos
    admin = login(api)["token"]
    email = "gestora@example.test"
    anterior = convidar(api, admin, email)
    convite = convidar(api, admin, email)
    assert aceitar(api, anterior).status_code == 409
    with banco() as sessao:
        sessao.get(ConviteConta, convite["convite"]["id"]).expira_em = agora_utc() - timedelta(seconds=1)
        sessao.commit()
    assert aceitar(api, convite).status_code == 409
    assert aceitar(api, convidar(api, admin, email)).status_code == 201
    pessoa = login(api, email)["token"]

    empresa_b = criar_empresa(api, admin, "Frutas Sul")
    resposta = api.post(f"/api/v1/empresas/{empresa_b}/convites", headers=headers(admin), json={"email": email})
    assert resposta.status_code == 201, resposta.text
    convite_b = resposta.json()
    assert aceitar(api, convite_b).status_code == 401
    assert aceitar(api, convite_b, token=admin).status_code == 403
    assert aceitar(api, convite_b, token=pessoa).status_code == 201
    assert api.get("/api/v1/equipe", headers=headers(pessoa, empresa_b)).status_code == 200
    assert api.post(f"/api/v1/empresas/{empresa_b}/convites", headers=headers(admin),
                    json={"email": "outra@example.test"}).status_code == 409


def test_integracao_restrita_a_empresa_com_segredo_revelado_uma_vez(api_acessos, banco):
    api, empresa_a, _ = api_acessos
    admin = login(api)["token"]
    empresa_b = criar_empresa(api, admin, "Frutas Sul")
    dados = {"nome": "GPS transportadora", "permissoes": ["integrar"],
             "expira_em": formatar_utc(agora_utc() + timedelta(days=1)), "recurso_tipo": "viagem", "recurso_id": "V-1"}
    resposta = api.post("/api/v1/integracoes", json=dados, headers=headers(admin))
    assert resposta.status_code == 201, resposta.text
    criada = resposta.json()
    token = criada["token"]
    with banco() as sessao:
        integracao = sessao.get(Integracao, criada["id"])
        assert (integracao.empresa_id, integracao.recurso_tipo, integracao.recurso_id) == (empresa_a, "viagem", "V-1")
        assert integracao.token_hash == autenticacao.hash_do_token(token)
    contexto = api.get("/api/v1/contexto", headers=headers(token))
    assert contexto.json()["empresa"]["permissoes"] == ["integrar"]
    assert api.get("/api/v1/contexto", headers=headers(token, empresa_b)).status_code == 403
    assert api.get("/api/v1/equipe", headers=headers(token)).status_code == 403
    assert api.get("/api/v1/empresas", headers=headers(token)).status_code == 401
    instancias = api.get("/api/v1/integracoes", headers=headers(admin)).json()
    assert "token" not in instancias[0] and instancias[0]["ultimo_uso_em"]
    assert api.delete(f"/api/v1/integracoes/{criada['id']}", headers=headers(admin)).status_code == 204
    assert api.get("/api/v1/contexto", headers=headers(token)).status_code == 401


def test_permissoes_de_papel_atualizam_sessao_sem_afetar_outra_empresa(api_acessos, banco):
    api, empresa_a, admin_id = api_acessos
    admin = login(api)["token"]
    email = "gestora@example.test"
    resposta = aceitar(api, convidar(api, admin, email))
    assert resposta.status_code == 201, resposta.text
    pessoa_id = resposta.json()["usuario"]["id"]
    gestor = login(api, email)["token"]
    empresa_b = criar_empresa(api, admin, "Frutas Sul")
    with banco() as sessao:
        sessao.add_all((VinculoConta(empresa_id=empresa_b, conta_id=admin_id, papel="administrador"),
                        VinculoConta(empresa_id=empresa_b, conta_id=pessoa_id, papel="gestor")))
        sessao.commit()

    papeis = api.get("/api/v1/papeis", headers=headers(admin, empresa_a)).json()
    assert {papel["papel"] for papel in papeis} == {"administrador", "gestor", "cliente"}
    assert api.patch("/api/v1/papeis/gestor", headers=headers(gestor, empresa_a),
                     json={"permissoes": []}).status_code == 403
    alteracao = api.patch("/api/v1/papeis/gestor", headers=headers(admin, empresa_a),
                          json={"permissoes": ["administrar"]})
    assert alteracao.status_code == 400
    admin_fixo = api.patch("/api/v1/papeis/administrador", headers=headers(admin, empresa_a),
                           json={"permissoes": []})
    assert admin_fixo.status_code == 409
    alterado = api.patch("/api/v1/papeis/gestor", headers=headers(admin, empresa_a),
                         json={"permissoes": ["consultar"]})
    assert alterado.status_code == 200, alterado.text
    assert api.get("/api/v1/contexto", headers=headers(gestor, empresa_a)).json()["empresa"]["permissoes"] == ["consultar"]
    assert "operar" in api.get("/api/v1/contexto", headers=headers(gestor, empresa_b)).json()["empresa"]["permissoes"]


def test_dois_aceites_simultaneos_criam_um_vinculo(monkeypatch, tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "convites.db")))
    banco = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def abrir_banco_teste():
        with banco() as sessao:
            yield sessao

    try:
        monkeypatch.setitem(app.dependency_overrides, abrir_sessao, abrir_banco_teste)
        with banco() as sessao:
            acessos.preparar_conta_inicial(sessao, "operacao", SENHA_INICIAL, "Frutas Norte")
            sessao.commit()
        api = TestClient(app)
        admin = login(api)["token"]
        convite = convidar(api, admin, "gestora@example.test")
        barreira = Barrier(2, timeout=10)

        def enviar_aceite():
            barreira.wait()
            return aceitar(TestClient(app), convite).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            aceites = [executor.submit(enviar_aceite) for _ in range(2)]
            assert sorted(aceite.result(timeout=20) for aceite in aceites) == [201, 409]
        with banco() as sessao:
            eventos = list(sessao.scalars(select(EventoAcesso).where(EventoAcesso.acao == "aceitar_convite")))
            assert len(eventos) == 1
            assert sessao.get(VinculoConta, (eventos[0].autor_id, eventos[0].empresa_id)) is not None
    finally:
        engine.dispose()
