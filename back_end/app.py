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
from starlette.exceptions import HTTPException

from config import CORS_ORIGENS
from controllers import frutas, lotes, monitoramento
from models.banco import Base, SessaoLocal, engine
from services.frutas import cadastrar_frutas_iniciais


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


# O contrato pede todos os erros no formato {"erro": "mensagem"}.
# O HTTPException do Starlette pega tambem rota inexistente (404) do proprio FastAPI.
@app.exception_handler(HTTPException)
async def tratar_erro_http(request: Request, erro: HTTPException):
    return JSONResponse(status_code=erro.status_code, content={"erro": erro.detail})


@app.exception_handler(RequestValidationError)
async def tratar_erro_validacao(request: Request, erro: RequestValidationError):
    # Mostra so o primeiro problema, com o nome do campo. Ex.: "fruta: Field required"
    primeiro = erro.errors()[0]
    campo = ".".join(str(parte) for parte in primeiro["loc"] if parte != "body")
    return JSONResponse(status_code=400, content={"erro": f"{campo}: {primeiro['msg']}"})


@app.get("/api/saude", tags=["saude"])
def saude():
    return {"status": "ok"}
