"""Rotas de alertas e de sincronizacao com o ThingSpeak."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from services.alertas import gerar_alertas
from services.sincronizacao import sincronizar
from services.thingspeak import ErroThingSpeak

router = APIRouter(prefix="/api", tags=["monitoramento"])


@router.get("/alertas")
def listar_alertas(sessao: Session = Depends(abrir_sessao)):
    return gerar_alertas(sessao)


@router.post("/sincronizar")
def sincronizar_thingspeak(sessao: Session = Depends(abrir_sessao)):
    try:
        return sincronizar(sessao)
    except ErroThingSpeak as erro:
        raise HTTPException(502, str(erro))
