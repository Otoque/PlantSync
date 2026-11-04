"""Rotas de alertas e de sincronizacao com o ThingSpeak."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from controllers.autenticacao import exigir_login
from models.banco import abrir_sessao
from services.alertas import gerar_alertas
from services.sincronizacao import sincronizar

# Todas as rotas deste arquivo exigem login.
router = APIRouter(prefix="/api", tags=["monitoramento"], dependencies=[Depends(exigir_login)])


@router.get("/alertas")
def listar_alertas(sessao: Session = Depends(abrir_sessao)):
    return gerar_alertas(sessao)


# Se o ThingSpeak estiver fora do ar, o app.py responde 502.
@router.post("/sincronizar")
def sincronizar_thingspeak(sessao: Session = Depends(abrir_sessao)):
    return sincronizar(sessao)
