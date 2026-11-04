"""
Testes do login simples: POST /api/login e /api/logout, protecao das rotas,
senha com hash e sal e usuario inicial vindo das variaveis de ambiente.
"""

import logging
from datetime import datetime, timedelta

from app import app
from auxiliares import (
    agora_utc,
    criar_lote,
    detalhe_do_lote,
    leituras_do_thingspeak,
    thingspeak_devolve,
)
from models.tabelas import SessaoDeLogin, Usuario
from services import autenticacao

SENHA = "senha usada so nos testes"
MENSAGEM_SEM_LOGIN = {"erro": "Faça login para continuar."}
MENSAGEM_LOGIN_INVALIDO = {"erro": "Usuário ou senha inválidos."}

# As unicas rotas da API que abrem sem login.
ROTAS_ABERTAS = [
    ("POST", "/api/login"),
    ("GET", "/api/saude"),
    ("GET", "/api/publico/{codigo}"),
    ("GET", "/api/laudos/{token}"),
]


# ---------- funcoes auxiliares deste arquivo ----------

def rotas_protegidas():
    """
    Lista (metodo, caminho) de toda rota /api fora das abertas. A lista vem do
    proprio app: uma rota nova que esquecer o login faz estes testes falharem.
    """
    rotas = []
    for caminho, metodos in app.openapi()["paths"].items():
        for metodo in metodos:
            if (metodo.upper(), caminho) not in ROTAS_ABERTAS:
                exemplo = caminho.replace("{lote_id}", "1").replace("{fruta_id}", "uva")
                rotas.append((metodo.upper(), exemplo))
    return rotas


def conferir_que_todas_dao_401(cliente, cabecalhos=None):
    rotas = rotas_protegidas()
    # 11 rotas: 3 de frutas, 5 de lotes, alertas, sincronizar e logout.
    assert len(rotas) == 11, rotas
    for metodo, caminho in rotas:
        resposta = cliente.request(metodo, caminho, headers=cabecalhos)
        assert resposta.status_code == 401, (metodo, caminho)
        assert resposta.json() == MENSAGEM_SEM_LOGIN, (metodo, caminho)


def criar_usuario(banco, nome="operador", senha=SENHA):
    with banco() as sessao:
        autenticacao.cadastrar_usuario(sessao, nome, senha)


def fazer_login(cliente, nome="operador", senha=SENHA):
    return cliente.post("/api/login", json={"usuario": nome, "senha": senha})


def cabecalho_de(token):
    return {"Authorization": f"Bearer {token}"}


def token_vencido(banco):
    """Abre uma sessao de login e muda a validade dela para o passado."""
    criar_usuario(banco, nome="usuario vencido")
    with banco() as sessao:
        usuario = sessao.query(Usuario).filter(Usuario.nome == "usuario vencido").first()
        token = autenticacao.abrir_sessao_de_login(sessao, usuario)["token"]
        linha = sessao.get(SessaoDeLogin, autenticacao.hash_do_token(token))
        linha.expira_em = agora_utc() - timedelta(minutes=1)
        sessao.commit()
    return token


def preparar_usuario(banco, nome, senha):
    with banco() as sessao:
        autenticacao.preparar_usuario_inicial(sessao, nome, senha)


def contar(banco, tabela):
    with banco() as sessao:
        return sessao.query(tabela).count()


# ---------- rotas protegidas ----------

def test_toda_rota_protegida_da_401_sem_token(cliente_sem_login):
    conferir_que_todas_dao_401(cliente_sem_login)


def test_toda_rota_protegida_da_401_com_token_invalido(cliente_sem_login):
    conferir_que_todas_dao_401(cliente_sem_login, cabecalho_de("token-que-nao-existe"))


def test_toda_rota_protegida_da_401_com_token_vencido(cliente_sem_login, banco):
    token = token_vencido(banco)
    conferir_que_todas_dao_401(cliente_sem_login, cabecalho_de(token))


def test_toda_rota_protegida_da_401_com_cabecalho_que_nao_e_bearer(cliente_sem_login):
    conferir_que_todas_dao_401(cliente_sem_login, {"Authorization": "Basic abc"})
    conferir_que_todas_dao_401(cliente_sem_login, {"Authorization": "Bearer"})


def test_resposta_401_avisa_o_esquema_de_login(cliente_sem_login):
    resposta = cliente_sem_login.get("/api/lotes")
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


def test_token_vencido_e_apagado_do_banco(cliente_sem_login, banco):
    token = token_vencido(banco)
    antes = contar(banco, SessaoDeLogin)
    cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token))
    assert contar(banco, SessaoDeLogin) == antes - 1


def test_token_que_ainda_vale_abre_a_rota(cliente_sem_login, banco):
    criar_usuario(banco)
    token = fazer_login(cliente_sem_login).json()["token"]
    resposta = cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token))
    assert resposta.status_code == 200


def test_sincronizacao_continua_funcionando_com_login(cliente, monkeypatch):
    thingspeak_devolve(monkeypatch, leituras_do_thingspeak(range(0, 3), 1.0))
    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200
    assert resposta.json()["novas"] == 3


# ---------- rotas abertas ----------

def test_saude_abre_sem_token(cliente_sem_login):
    assert cliente_sem_login.get("/api/saude").status_code == 200


def test_visao_publica_e_laudo_abrem_sem_token(cliente, cliente_sem_login):
    lote = criar_lote(cliente)
    detalhe = detalhe_do_lote(cliente, lote)

    publica = cliente_sem_login.get(f"/api/publico/{detalhe['codigo_publico']}")
    laudo = cliente_sem_login.get(f"/api/laudos/{detalhe['token_laudo']}")

    assert publica.status_code == 200
    assert laudo.status_code == 200


# ---------- POST /api/login ----------

def test_login_devolve_token_e_validade_de_8_horas(cliente_sem_login, banco):
    criar_usuario(banco)
    resposta = fazer_login(cliente_sem_login)
    assert resposta.status_code == 200

    corpo = resposta.json()
    assert sorted(corpo) == ["expira_em", "token"]
    expira_em = datetime.strptime(corpo["expira_em"], "%Y-%m-%dT%H:%M:%SZ")
    falta = expira_em - agora_utc()
    assert timedelta(hours=7, minutes=59) < falta <= timedelta(hours=8)


def test_cada_login_gera_um_token_diferente(cliente_sem_login, banco):
    criar_usuario(banco)
    primeiro = fazer_login(cliente_sem_login).json()["token"]
    segundo = fazer_login(cliente_sem_login).json()["token"]
    assert primeiro != segundo


def test_banco_guarda_o_hash_do_token_e_nao_o_token(cliente_sem_login, banco):
    criar_usuario(banco)
    token = fazer_login(cliente_sem_login).json()["token"]
    with banco() as sessao:
        assert sessao.get(SessaoDeLogin, token) is None
        assert sessao.get(SessaoDeLogin, autenticacao.hash_do_token(token)) is not None


def test_senha_errada_e_usuario_inexistente_dao_a_mesma_resposta(cliente_sem_login, banco):
    criar_usuario(banco)
    senha_errada = fazer_login(cliente_sem_login, senha="outra senha")
    usuario_errado = fazer_login(cliente_sem_login, nome="ninguem")
    assert senha_errada.status_code == 401
    assert usuario_errado.status_code == 401
    assert senha_errada.json() == MENSAGEM_LOGIN_INVALIDO
    assert usuario_errado.json() == MENSAGEM_LOGIN_INVALIDO


def test_usuario_inexistente_tambem_calcula_o_hash(cliente_sem_login, monkeypatch):
    # Senao a resposta sairia mais rapido e revelaria quais usuarios existem.
    chamadas = []
    original = autenticacao.calcular_hash_da_senha

    def contar_chamada(senha, sal):
        chamadas.append(sal)
        return original(senha, sal)

    monkeypatch.setattr(autenticacao, "calcular_hash_da_senha", contar_chamada)
    fazer_login(cliente_sem_login, nome="ninguem")
    assert len(chamadas) == 1


def test_login_com_campo_faltando_vazio_ou_longo_demais_da_400(cliente_sem_login):
    corpos = [
        {"usuario": "operador"},
        {"senha": SENHA},
        {"usuario": "", "senha": SENHA},
        {"usuario": "operador", "senha": ""},
        {"usuario": "operador", "senha": "x" * 201},
        {"usuario": "x" * 101, "senha": SENHA},
    ]
    for corpo in corpos:
        resposta = cliente_sem_login.post("/api/login", json=corpo)
        assert resposta.status_code == 400, corpo


def test_senha_com_caractere_invalido_nao_derruba_o_login(cliente_sem_login):
    # \ud800 e um caractere pela metade: nao da para codificar em UTF-8.
    corpo = '{"usuario": "operador", "senha": "\\ud800"}'
    cabecalho = {"Content-Type": "application/json"}
    resposta = cliente_sem_login.post("/api/login", content=corpo, headers=cabecalho)
    assert resposta.status_code in (400, 401)


def test_login_apaga_as_sessoes_vencidas(cliente_sem_login, banco):
    vencido = token_vencido(banco)
    criar_usuario(banco)
    fazer_login(cliente_sem_login)
    with banco() as sessao:
        assert sessao.get(SessaoDeLogin, autenticacao.hash_do_token(vencido)) is None


# ---------- POST /api/logout ----------

def test_logout_encerra_a_sessao(cliente_sem_login, banco):
    criar_usuario(banco)
    token = fazer_login(cliente_sem_login).json()["token"]

    resposta = cliente_sem_login.post("/api/logout", headers=cabecalho_de(token))
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "sessão encerrada"}

    depois = cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token))
    assert depois.status_code == 401


def test_logout_nao_derruba_as_outras_sessoes(cliente_sem_login, banco):
    criar_usuario(banco)
    primeiro = fazer_login(cliente_sem_login).json()["token"]
    segundo = fazer_login(cliente_sem_login).json()["token"]

    cliente_sem_login.post("/api/logout", headers=cabecalho_de(primeiro))

    assert cliente_sem_login.get("/api/lotes", headers=cabecalho_de(segundo)).status_code == 200


# ---------- senha ----------

def test_senha_e_guardada_so_como_hash_com_sal_diferente_por_usuario(banco):
    criar_usuario(banco, nome="primeiro")
    criar_usuario(banco, nome="segundo")
    with banco() as sessao:
        primeiro = sessao.query(Usuario).filter(Usuario.nome == "primeiro").first()
        segundo = sessao.query(Usuario).filter(Usuario.nome == "segundo").first()
        assert SENHA not in primeiro.senha_hash
        assert primeiro.sal != segundo.sal
        assert primeiro.senha_hash != segundo.senha_hash


def test_senha_nunca_aparece_em_resposta_nem_em_log(cliente_sem_login, banco, caplog):
    caplog.set_level(logging.DEBUG)
    preparar_usuario(banco, "operador", SENHA)
    preparar_usuario(banco, "operador", SENHA)

    respostas = [
        fazer_login(cliente_sem_login),
        fazer_login(cliente_sem_login, nome="ninguem"),
        fazer_login(cliente_sem_login, nome="operador", senha=SENHA + " errada"),
        cliente_sem_login.post("/api/login", json={"senha": SENHA}),
        cliente_sem_login.post("/api/login", json={"usuario": 1, "senha": SENHA}),
    ]

    for resposta in respostas:
        assert SENHA not in resposta.text
    assert SENHA not in caplog.text


# ---------- usuario inicial vindo das variaveis de ambiente ----------

def test_usuario_inicial_consegue_entrar(cliente_sem_login, banco):
    preparar_usuario(banco, "operador", SENHA)
    assert fazer_login(cliente_sem_login).status_code == 200


def test_sem_variaveis_ninguem_entra_e_o_log_avisa(cliente_sem_login, banco, caplog):
    caplog.set_level(logging.WARNING)
    for nome, senha in [(None, None), ("operador", None), (None, SENHA), ("", "")]:
        preparar_usuario(banco, nome, senha)
    assert contar(banco, Usuario) == 0
    assert "PLANTSYNC_USUARIO" in caplog.text
    assert fazer_login(cliente_sem_login).status_code == 401


def test_tirar_as_variaveis_tira_o_usuario_e_as_sessoes(cliente_sem_login, banco):
    preparar_usuario(banco, "operador", SENHA)
    token = fazer_login(cliente_sem_login).json()["token"]

    preparar_usuario(banco, None, None)

    assert fazer_login(cliente_sem_login).status_code == 401
    assert cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token)).status_code == 401


def test_trocar_a_senha_derruba_a_antiga_e_as_sessoes(cliente_sem_login, banco):
    preparar_usuario(banco, "operador", SENHA)
    token = fazer_login(cliente_sem_login).json()["token"]

    preparar_usuario(banco, "operador", "senha nova de teste")

    assert fazer_login(cliente_sem_login).status_code == 401
    assert fazer_login(cliente_sem_login, senha="senha nova de teste").status_code == 200
    assert cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token)).status_code == 401


def test_trocar_o_usuario_tira_o_antigo(cliente_sem_login, banco):
    preparar_usuario(banco, "operador", SENHA)
    preparar_usuario(banco, "gestor", SENHA)
    assert fazer_login(cliente_sem_login, nome="operador").status_code == 401
    assert fazer_login(cliente_sem_login, nome="gestor").status_code == 200


def test_reiniciar_com_as_mesmas_variaveis_mantem_as_sessoes(cliente_sem_login, banco):
    preparar_usuario(banco, "operador", SENHA)
    token = fazer_login(cliente_sem_login).json()["token"]

    preparar_usuario(banco, "operador", SENHA)

    assert cliente_sem_login.get("/api/lotes", headers=cabecalho_de(token)).status_code == 200


# ---------- CORS ----------

def test_cors_aceita_o_cabecalho_authorization(cliente_sem_login):
    resposta = cliente_sem_login.options("/api/lotes", headers={
        "Origin": "http://localhost:5500",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert resposta.status_code == 200
    permitidos = resposta.headers["Access-Control-Allow-Headers"].lower()
    assert "authorization" in permitidos
    assert "content-type" in permitidos


def test_resposta_401_tem_cors_para_o_painel_conseguir_ler(cliente_sem_login):
    resposta = cliente_sem_login.get("/api/lotes", headers={"Origin": "http://localhost:5500"})
    assert resposta.status_code == 401
    assert resposta.headers["Access-Control-Allow-Origin"] == "http://localhost:5500"
