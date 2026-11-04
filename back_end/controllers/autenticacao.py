"""Rotas de login e logout, e a protecao usada pelas outras rotas."""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.entradas import DadosDeLogin
from services import autenticacao
from services.erros import ErroNaoAutenticado

router = APIRouter(prefix="/api", tags=["login"])

# Le o cabecalho "Authorization: Bearer <token>" e cria o botao Authorize em /docs.
# Com auto_error=False, o erro de login sai no nosso formato, em portugues.
esquema_bearer = HTTPBearer(auto_error=False)


def exigir_login(credenciais=Depends(esquema_bearer), sessao: Session = Depends(abrir_sessao)):
    """Protege uma rota: sem token valido, a resposta e 401. Devolve o token."""
    if credenciais is None:
        raise ErroNaoAutenticado(autenticacao.MENSAGEM_SEM_LOGIN)
    autenticacao.conferir_token(sessao, credenciais.credentials)
    return credenciais.credentials


@router.post("/login")
def fazer_login(dados: DadosDeLogin, sessao: Session = Depends(abrir_sessao)):
    return autenticacao.fazer_login(sessao, dados.usuario, dados.senha)


@router.post("/logout")
def fazer_logout(token: str = Depends(exigir_login), sessao: Session = Depends(abrir_sessao)):
    autenticacao.encerrar_token_de_acesso(sessao, token)
    return {"status": "sessão encerrada"}
