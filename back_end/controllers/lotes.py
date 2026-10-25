"""Rotas dos lotes: cadastro, consulta, encerramento e leituras."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.entradas import Encerramento, LoteNovo
from models.tabelas import Fruta, Lote
from services.datas import agora_utc, para_utc
from services.frutas import validar_faixa
from services.lotes import (
    analisar,
    faixa_do_lote,
    leitura_para_json,
    leituras_do_lote,
    lote_detalhado_json,
    lote_em_transito,
    lote_para_json,
)

router = APIRouter(prefix="/api/lotes", tags=["lotes"])


def buscar_lote(sessao, lote_id):
    lote = sessao.get(Lote, lote_id)
    if lote is None:
        raise HTTPException(404, f"Lote {lote_id} não encontrado.")
    return lote


@router.get("")
def listar_lotes(sessao: Session = Depends(abrir_sessao)):
    lotes = sessao.query(Lote).order_by(Lote.inicio.desc()).all()
    return [lote_para_json(lote, analisar(sessao, lote)) for lote in lotes]


@router.post("", status_code=201)
def cadastrar_lote(dados: LoteNovo, sessao: Session = Depends(abrir_sessao)):
    fruta = sessao.get(Fruta, dados.fruta)
    if fruta is None:
        ids = ", ".join(f.id for f in sessao.query(Fruta).order_by(Fruta.id).all())
        raise HTTPException(400, f"Fruta '{dados.fruta}' não cadastrada. Use: {ids}.")

    # Existe um so sensor (um canal), entao so um lote viaja por vez.
    atual = lote_em_transito(sessao)
    if atual is not None:
        raise HTTPException(400, f"O lote {atual.id} ainda está em trânsito. Encerre-o antes de cadastrar outro.")

    # Sem faixa propria, o lote copia a faixa atual da fruta.
    faixa = dados.faixa_segura
    if faixa is None:
        faixa = fruta
    else:
        erro = validar_faixa(faixa)
        if erro:
            raise HTTPException(400, erro)

    inicio = agora_utc()
    if dados.inicio is not None:
        inicio = para_utc(dados.inicio)

    lote = Lote(
        fruta_id=fruta.id,
        origem=dados.origem,
        porto_destino=dados.porto_destino,
        inicio=inicio,
        fim=None,
        temp_min_c=faixa.temp_min_c,
        temp_max_c=faixa.temp_max_c,
        umidade_min_pct=faixa.umidade_min_pct,
        umidade_max_pct=faixa.umidade_max_pct,
    )
    sessao.add(lote)
    sessao.commit()
    return lote_para_json(lote, analisar(sessao, lote))


@router.get("/{lote_id}")
def ver_lote(lote_id: int, sessao: Session = Depends(abrir_sessao)):
    lote = buscar_lote(sessao, lote_id)
    return lote_detalhado_json(lote, analisar(sessao, lote))


@router.post("/{lote_id}/encerrar")
def encerrar_lote(lote_id: int, dados: Encerramento | None = None, sessao: Session = Depends(abrir_sessao)):
    lote = buscar_lote(sessao, lote_id)
    if lote.fim is not None:
        raise HTTPException(400, f"O lote {lote_id} já foi encerrado.")

    fim = agora_utc()
    if dados is not None and dados.fim is not None:
        fim = para_utc(dados.fim)
    if fim < lote.inicio:
        raise HTTPException(400, "O fim não pode ser anterior ao início do lote.")

    lote.fim = fim
    sessao.commit()
    return lote_para_json(lote, analisar(sessao, lote))


@router.get("/{lote_id}/leituras")
def listar_leituras(lote_id: int, sessao: Session = Depends(abrir_sessao)):
    lote = buscar_lote(sessao, lote_id)
    faixa = faixa_do_lote(lote)
    return [leitura_para_json(leitura, faixa) for leitura in leituras_do_lote(sessao, lote)]
