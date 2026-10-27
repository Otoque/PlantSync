"""Rotas das frutas e suas faixas seguras."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.entradas import FrutaDados, FrutaNova
from services import frutas

router = APIRouter(prefix="/api/frutas", tags=["frutas"])


@router.get("")
def listar_frutas(sessao: Session = Depends(abrir_sessao)):
    return [frutas.fruta_para_json(fruta) for fruta in frutas.todas_as_frutas(sessao)]


@router.post("", status_code=201)
def cadastrar_fruta(dados: FrutaNova, sessao: Session = Depends(abrir_sessao)):
    fruta = frutas.criar_fruta(sessao, dados)
    return frutas.fruta_para_json(fruta)


@router.put("/{fruta_id}")
def editar_fruta(fruta_id: str, dados: FrutaDados, sessao: Session = Depends(abrir_sessao)):
    fruta = frutas.atualizar_fruta(sessao, fruta_id, dados)
    return frutas.fruta_para_json(fruta)
