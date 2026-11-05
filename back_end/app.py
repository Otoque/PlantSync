"""
API do PlantSync.

Para rodar (dentro da pasta back_end):
    uvicorn app:app --reload --port 8000

Documentacao interativa: http://localhost:8000/docs
Contrato completo: docs/api-contrato.md
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# O FastAPI usa o HTTPException do Starlette por baixo. Tratando o do Starlette,
# pegamos tambem o 404 de rota inexistente, que o proprio FastAPI levanta.
from starlette.exceptions import HTTPException

from config import (
    CORS_ORIGENS,
    PLANTSYNC_CHAVE_DISPOSITIVO,
    PLANTSYNC_SENHA,
    PLANTSYNC_USUARIO,
)
from controllers import autenticacao, dispositivo, frutas, laudos, lotes, monitoramento
from models.banco import Base, SessaoLocal, engine
from services.autenticacao import preparar_usuario_inicial
from services.dispositivo import avisar_se_a_chave_for_invalida
from services.erros import (
    ErroChaveDoDispositivo,
    ErroDeRegra,
    ErroDispositivoNaoConfigurado,
    ErroNaoAutenticado,
    ErroNaoEncontrado,
    ErroThingSpeak,
)
from services.frutas import cadastrar_frutas_iniciais


# Formato pedido pelo FastAPI para rodar algo quando o servidor liga:
# o que vem antes do yield roda ao ligar; o que viesse depois rodaria ao desligar.
@asynccontextmanager
async def ao_iniciar(app):
    """Cria as tabelas e as frutas iniciais e prepara o usuario de login."""
    Base.metadata.create_all(engine)
    with SessaoLocal() as sessao:
        cadastrar_frutas_iniciais(sessao)
        preparar_usuario_inicial(sessao, PLANTSYNC_USUARIO, PLANTSYNC_SENHA)
    avisar_se_a_chave_for_invalida(PLANTSYNC_CHAVE_DISPOSITIVO)
    yield


app = FastAPI(title="PlantSync API", version="0.3", lifespan=ao_iniciar)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(autenticacao.router)
app.include_router(frutas.router)
app.include_router(lotes.router)
app.include_router(monitoramento.router)
app.include_router(laudos.router)
app.include_router(dispositivo.router)


# Todos os erros saem no formato do contrato: {"erro": "mensagem"}.

# Traducao dos erros mais comuns do FastAPI e do Pydantic, que vem em ingles.
# Erro que nao estiver aqui sai com a mensagem original.
MENSAGENS_HTTP = {
    404: "Rota não encontrada.",
    405: "Método não permitido nesta rota.",
}
MENSAGENS_VALIDACAO = {
    "missing": "campo obrigatório",
    "float_parsing": "precisa ser um número",
    "float_type": "precisa ser um número",
    "finite_number": "precisa ser um número finito",
    "int_parsing": "precisa ser um número inteiro",
    "string_type": "precisa ser um texto",
    "string_too_short": "não pode ficar vazio",
    "string_too_long": "texto longo demais",
    "string_pattern_mismatch": "formato inválido",
    "greater_than_equal": "valor abaixo do mínimo permitido",
    "less_than_equal": "valor acima do máximo permitido",
    "datetime_parsing": "data inválida (use o formato 2026-10-24T09:00:00Z)",
    "datetime_from_date_parsing": "data inválida (use o formato 2026-10-24T09:00:00Z)",
    "json_invalid": "JSON inválido",
}


def resposta_de_erro(codigo, mensagem):
    return JSONResponse(status_code=codigo, content={"erro": mensagem})


@app.exception_handler(ErroDeRegra)
def tratar_erro_de_regra(request: Request, erro: ErroDeRegra):
    return resposta_de_erro(400, str(erro))


@app.exception_handler(ErroNaoAutenticado)
def tratar_nao_autenticado(request: Request, erro: ErroNaoAutenticado):
    # O cabecalho WWW-Authenticate avisa qual tipo de login a API espera.
    resposta = resposta_de_erro(401, str(erro))
    resposta.headers["WWW-Authenticate"] = "Bearer"
    return resposta


@app.exception_handler(ErroChaveDoDispositivo)
def tratar_chave_do_dispositivo(request: Request, erro: ErroChaveDoDispositivo):
    return resposta_de_erro(401, str(erro))


@app.exception_handler(ErroDispositivoNaoConfigurado)
def tratar_dispositivo_nao_configurado(request: Request, erro: ErroDispositivoNaoConfigurado):
    return resposta_de_erro(503, str(erro))


@app.exception_handler(ErroNaoEncontrado)
def tratar_nao_encontrado(request: Request, erro: ErroNaoEncontrado):
    return resposta_de_erro(404, str(erro))


@app.exception_handler(ErroThingSpeak)
def tratar_erro_thingspeak(request: Request, erro: ErroThingSpeak):
    return resposta_de_erro(502, str(erro))


@app.exception_handler(HTTPException)
def tratar_erro_http(request: Request, erro: HTTPException):
    mensagem = MENSAGENS_HTTP.get(erro.status_code, erro.detail)
    return resposta_de_erro(erro.status_code, mensagem)


@app.exception_handler(RequestValidationError)
def tratar_erro_validacao(request: Request, erro: RequestValidationError):
    """Mostra so o primeiro campo com problema. Ex.: "fruta: campo obrigatório"."""
    primeiro = erro.errors()[0]
    mensagem = MENSAGENS_VALIDACAO.get(primeiro["type"], primeiro["msg"])

    # JSON quebrado nao tem campo: o "loc" traz a posicao do caractere.
    if primeiro["type"] == "json_invalid":
        return resposta_de_erro(400, mensagem + ".")

    # "loc" e o caminho do campo, ex.: ["body", "faixa_segura", "temp_min_c"].
    # Tiramos o "body" e juntamos o resto com ponto: "faixa_segura.temp_min_c".
    partes = []
    for parte in primeiro["loc"]:
        if parte != "body":
            partes.append(str(parte))
    campo = ".".join(partes)
    return resposta_de_erro(400, f"{campo}: {mensagem}")


@app.get("/api/saude", tags=["saude"])
def saude():
    return {"status": "ok"}
