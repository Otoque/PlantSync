"""Toda nova rota operacional deve negar acesso anônimo, salvo capacidades públicas."""

import re

from app import app


ROTAS_PUBLICAS = {
    ("POST", "/api/v1/login"),
    ("POST", "/api/v1/convites/aceitar"),
    ("GET", "/api/v1/publico/{codigo}"),
    ("GET", "/api/v1/laudos/{token}"),
}


def test_superficie_operacional_nega_acesso_anonimo(cliente_sem_login):
    verificadas = set()
    for caminho, metodos in app.openapi()["paths"].items():
        if not caminho.startswith("/api/v1/"):
            continue
        for metodo in metodos:
            rota = (metodo.upper(), caminho)
            if rota in ROTAS_PUBLICAS:
                continue
            concreto = re.sub(r"\{[^}]+\}", "1", caminho)
            resposta = cliente_sem_login.request(metodo.upper(), concreto)
            assert resposta.status_code == 401, (rota, resposta.status_code, resposta.text)
            verificadas.add(rota)
    assert ("GET", "/api/v1/contexto") in verificadas
    assert ("GET", "/api/v1/perfil") in verificadas


def test_token_legado_nao_abre_api_por_empresa(cliente):
    resposta = cliente.get("/api/v1/contexto")
    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


def test_cutover_desativa_acesso_interno_legado(cliente, monkeypatch):
    monkeypatch.setattr(app.state, "legado_convertido", True, raising=False)
    assert cliente.get("/api/lotes").status_code == 410
    assert cliente.post("/api/login", json={"usuario": "antigo", "senha": "antiga"}).status_code == 410
    assert cliente.get("/api/saude").status_code == 200
    assert cliente.get("/api/v1/contexto").status_code == 401


def test_nova_operacao_nao_abre_catalogo_global_pela_api_antiga(cliente, monkeypatch):
    monkeypatch.setattr(app.state, "legado_convertido", False, raising=False)
    monkeypatch.setattr(app.state, "operacao_inicializada", True, raising=False)
    assert cliente.get("/api/frutas").status_code == 410
    assert cliente.post("/api/login", json={"usuario": "antigo", "senha": "antiga"}).status_code == 410
