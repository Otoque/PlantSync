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

from config import CORS_ORIGENS
from controllers import frutas, lotes, monitoramento
from models.banco import Base, SessaoLocal, engine
from services.erros import ErroDeRegra, ErroNaoEncontrado, ErroThingSpeak
from services.frutas import cadastrar_frutas_iniciais


# Formato pedido pelo FastAPI para rodar algo quando o servidor liga:
# o que vem antes do yield roda ao ligar; o que viesse depois rodaria ao desligar.
@asynccontextmanager
async def ao_iniciar(app):
    """Cria as tabelas e as frutas iniciais na primeira execucao."""
    Base.metadata.create_all(engine)
    with SessaoLocal() as sessao:
        cadastrar_frutas_iniciais(sessao)
    yield


app = FastAPI(title="PlantSync API", version="0.3", lifespan=ao_iniciar)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(frutas.router)
app.include_router(lotes.router)
app.include_router(monitoramento.router)


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
    "int_parsing": "precisa ser um número inteiro",
    "string_type": "precisa ser um texto",
    "string_too_short": "não pode ficar vazio",
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
