"""Rotas das frutas e suas faixas seguras."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.entradas import FrutaEdicao, FrutaNova
from models.tabelas import Fruta
from services.frutas import fruta_para_json, validar_faixa

router = APIRouter(prefix="/api/frutas", tags=["frutas"])


@router.get("")
def listar_frutas(sessao: Session = Depends(abrir_sessao)):
    frutas = sessao.query(Fruta).order_by(Fruta.id).all()
    return [fruta_para_json(fruta) for fruta in frutas]


@router.post("", status_code=201)
def cadastrar_fruta(dados: FrutaNova, sessao: Session = Depends(abrir_sessao)):
    erro = validar_faixa(dados)
    if erro:
        raise HTTPException(400, erro)
    if sessao.get(Fruta, dados.id) is not None:
        raise HTTPException(400, f"A fruta '{dados.id}' já existe.")

    fruta = Fruta(**dados.model_dump())
    sessao.add(fruta)
    sessao.commit()
    return fruta_para_json(fruta)


@router.put("/{fruta_id}")
def editar_fruta(fruta_id: str, dados: FrutaEdicao, sessao: Session = Depends(abrir_sessao)):
    fruta = sessao.get(Fruta, fruta_id)
    if fruta is None:
        raise HTTPException(404, f"Fruta '{fruta_id}' não encontrada.")
    erro = validar_faixa(dados)
    if erro:
        raise HTTPException(400, erro)

    # So muda a fruta. Os lotes ja criados guardam a propria copia da faixa.
    fruta.nome = dados.nome
    fruta.fonte = dados.fonte
    fruta.temp_min_c = dados.temp_min_c
    fruta.temp_max_c = dados.temp_max_c
    fruta.umidade_min_pct = dados.umidade_min_pct
    fruta.umidade_max_pct = dados.umidade_max_pct
    sessao.commit()
    return fruta_para_json(fruta)
