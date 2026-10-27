"""Rotas dos lotes: cadastro, consulta, encerramento e leituras."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.entradas import Encerramento, LoteNovo
from services import lotes

router = APIRouter(prefix="/api/lotes", tags=["lotes"])


@router.get("")
def listar_lotes(sessao: Session = Depends(abrir_sessao)):
    resposta = []
    for lote in lotes.todos_os_lotes(sessao):
        resposta.append(lotes.lote_resumo_json(sessao, lote))
    return resposta


@router.post("", status_code=201)
def cadastrar_lote(dados: LoteNovo, sessao: Session = Depends(abrir_sessao)):
    lote = lotes.criar_lote(sessao, dados)
    return lotes.lote_resumo_json(sessao, lote)


@router.get("/{lote_id}")
def ver_lote(lote_id: int, sessao: Session = Depends(abrir_sessao)):
    lote = lotes.buscar_lote(sessao, lote_id)
    return lotes.lote_detalhado_json(lote, lotes.buscar_e_analisar(sessao, lote))


# O corpo e opcional: sem corpo, o FastAPI usa o Encerramento() vazio (fim = None).
@router.post("/{lote_id}/encerrar")
def encerrar_lote(
    lote_id: int,
    dados: Encerramento = Encerramento(),
    sessao: Session = Depends(abrir_sessao),
):
    lote = lotes.buscar_lote(sessao, lote_id)
    lote = lotes.registrar_fim_do_lote(sessao, lote, dados.fim)
    return lotes.lote_resumo_json(sessao, lote)


@router.get("/{lote_id}/leituras")
def listar_leituras(lote_id: int, sessao: Session = Depends(abrir_sessao)):
    lote = lotes.buscar_lote(sessao, lote_id)
    return lotes.leituras_para_grafico(sessao, lote)
