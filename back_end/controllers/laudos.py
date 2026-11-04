"""Rotas do laudo por QR Code: visao publica e laudo completo."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from services import laudos

router = APIRouter(prefix="/api", tags=["laudos"])


@router.get("/publico/{codigo}")
def ver_visao_publica(codigo: str, sessao: Session = Depends(abrir_sessao)):
    lote = laudos.buscar_por_codigo_publico(sessao, codigo)
    return laudos.visao_publica_json(sessao, lote)


@router.get("/laudos/{token}")
def ver_laudo_completo(token: str, sessao: Session = Depends(abrir_sessao)):
    lote = laudos.buscar_por_token(sessao, token)
    return laudos.laudo_completo_json(sessao, lote)
