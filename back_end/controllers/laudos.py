"""Rotas do laudo por QR Code: visao publica e laudo completo."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.migracoes import RegistroMigracao
from services import laudos

router = APIRouter(prefix="/api", tags=["laudos"])


@router.get("/publico/{codigo}")
def ver_visao_publica(codigo: str, sessao: Session = Depends(abrir_sessao)):
    if sessao.get(RegistroMigracao, "legado_para_operacao_v1") is not None:
        from services.operacao_monitoramento import resumo_publico
        dados = resumo_publico(sessao, codigo)
        dados["selo_faixa_segura"] = dados["seal"]["elegivel"]
        return dados
    lote = laudos.buscar_por_codigo_publico(sessao, codigo)
    return laudos.visao_publica_json(sessao, lote)


@router.get("/laudos/{token}")
def ver_laudo_completo(token: str, sessao: Session = Depends(abrir_sessao)):
    if sessao.get(RegistroMigracao, "legado_para_operacao_v1") is not None:
        from services.operacao_monitoramento import laudo_secreto
        return laudo_secreto(sessao, token)
    lote = laudos.buscar_por_token(sessao, token)
    return laudos.laudo_completo_json(sessao, lote)
