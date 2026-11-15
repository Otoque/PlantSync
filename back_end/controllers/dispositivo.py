"""Rota usada pela placa. Abre so com a chave do dispositivo, nunca com o login."""

from fastapi import APIRouter, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from config import PLANTSYNC_CHAVE_DISPOSITIVO
from models.banco import abrir_sessao
from services import dispositivo

# Le o cabecalho X-Chave-Dispositivo. Com auto_error=False, o erro sai no nosso formato.
esquema_chave = APIKeyHeader(name="X-Chave-Dispositivo", auto_error=False)


def exigir_chave_do_dispositivo(chave=Depends(esquema_chave)):
    dispositivo.conferir_chave(chave, PLANTSYNC_CHAVE_DISPOSITIVO)


router = APIRouter(
    prefix="/api/dispositivo",
    tags=["dispositivo"],
    dependencies=[Depends(exigir_chave_do_dispositivo)],
)


@router.get("/faixa")
def ver_faixa(sessao: Session = Depends(abrir_sessao)):
    return dispositivo.faixa_para_a_placa(sessao)
