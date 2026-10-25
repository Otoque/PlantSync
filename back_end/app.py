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
from services.erros import ErroDeRegra, NaoEncontrado
from services.frutas import cadastrar_frutas_iniciais
from services.thingspeak import ErroThingSpeak


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

def resposta_de_erro(codigo, mensagem):
    return JSONResponse(status_code=codigo, content={"erro": mensagem})


@app.exception_handler(ErroDeRegra)
def tratar_erro_de_regra(request: Request, erro: ErroDeRegra):
    return resposta_de_erro(400, str(erro))


@app.exception_handler(NaoEncontrado)
def tratar_nao_encontrado(request: Request, erro: NaoEncontrado):
    return resposta_de_erro(404, str(erro))


@app.exception_handler(ErroThingSpeak)
def tratar_erro_thingspeak(request: Request, erro: ErroThingSpeak):
    return resposta_de_erro(502, str(erro))


@app.exception_handler(HTTPException)
def tratar_erro_http(request: Request, erro: HTTPException):
    return resposta_de_erro(erro.status_code, erro.detail)


@app.exception_handler(RequestValidationError)
def tratar_erro_validacao(request: Request, erro: RequestValidationError):
    """Mostra so o primeiro campo com problema. Ex.: "fruta: Field required"."""
    primeiro = erro.errors()[0]

    # "loc" e o caminho do campo, ex.: ["body", "faixa_segura", "temp_min_c"].
    # Tiramos o "body" e juntamos o resto com ponto: "faixa_segura.temp_min_c".
    partes = []
    for parte in primeiro["loc"]:
        if parte != "body":
            partes.append(str(parte))
    campo = ".".join(partes)
    return resposta_de_erro(400, f"{campo}: {primeiro['msg']}")


@app.get("/api/saude", tags=["saude"])
def saude():
    return {"status": "ok"}
