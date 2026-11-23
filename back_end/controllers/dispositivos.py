"""Cadastro de placas pelo painel. Nenhuma chave faz parte da resposta."""

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import CANAL_THINGSPEAK
from controllers.autenticacao import exigir_login
from models.banco import abrir_sessao
from models.entradas import DispositivoNovo
from models.tabelas import Dispositivo, VinculoDispositivo
from services.erros import ErroDeRegra
from services.lotes import lote_em_transito

router = APIRouter(
    prefix="/api/dispositivos", tags=["dispositivos"], dependencies=[Depends(exigir_login)],
)


def placa_json(placa, ocupado=False):
    return {"id": placa.id, "nome": placa.nome, "canal": placa.canal, "ocupado": ocupado}


@router.get("")
def listar_dispositivos(sessao: Session = Depends(abrir_sessao)):
    placas = sessao.query(Dispositivo).order_by(Dispositivo.nome, Dispositivo.id).all()
    ocupados = {item.ocupacao for item in sessao.query(VinculoDispositivo).filter(
        VinculoDispositivo.ocupacao.is_not(None)
    )}
    padrao = {
        "id": None, "nome": "Placa padrão", "canal": CANAL_THINGSPEAK,
        "ocupado": lote_em_transito(sessao) is not None or any(p.canal == CANAL_THINGSPEAK for p in placas),
    }
    return [padrao] + [placa_json(p, p.id in ocupados) for p in placas]


@router.post("", status_code=201)
def cadastrar_dispositivo(dados: DispositivoNovo, sessao: Session = Depends(abrir_sessao)):
    nome = dados.nome.strip()
    if not nome:
        raise ErroDeRegra("Informe um nome para a placa.")
    if dados.canal == CANAL_THINGSPEAK:
        raise ErroDeRegra("Esse canal já é usado pela placa padrão.")
    placa = Dispositivo(nome=nome, canal=dados.canal)
    sessao.add(placa)
    try:
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        if sessao.query(Dispositivo).filter_by(canal=dados.canal).first():
            raise ErroDeRegra("Esse canal já pertence a uma placa cadastrada.") from erro
        raise
    return placa_json(placa)
