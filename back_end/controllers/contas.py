"""Rotas de sessão, gestão de empresas, equipe e integrações."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.contas import ConviteConta, Empresa, EventoAcesso, Integracao, SessaoConta
from services import acessos
from services.datas import agora_utc, formatar_utc


router = APIRouter(prefix="/api/v1", tags=["contas e empresas"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Senha = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
Identificador = Annotated[int, Path(gt=0, le=2**63 - 1)]
Papel = Literal["administrador", "gestor", "cliente"]
Escopo = Literal["consultar", "operar", "receber", "integrar"]
Permissao = Literal["consultar", "operar", "compartilhar", "receber", "etiquetas", "administrar", "integrar"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Entrada):
    usuario: Annotated[str, StringConstraints(max_length=254)]
    senha: Senha


class TrocaSenha(Entrada):
    senha_atual: Senha
    nova_senha: Senha


class DadosEmpresa(Entrada):
    nome: Nome


class AlteracaoEmpresa(Entrada):
    nome: Nome | None = None
    ativo: bool | None = None


class AlteracaoVinculo(Entrada):
    papel: Papel | None = None
    ativo: bool | None = None


class AlteracaoPapel(Entrada):
    permissoes: set[Permissao]


class Convite(Entrada):
    email: Email
    papel: Papel


class ConviteAdministrador(Entrada):
    email: Email


class Aceite(Entrada):
    token: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    email: Email
    nome: Nome | None = None
    senha: Senha | None = None


class DadosIntegracao(Entrada):
    nome: Nome
    permissoes: Annotated[set[Escopo], Field(min_length=1)]
    expira_em: datetime
    recurso_tipo: Literal["lote", "viagem", "sensor"] | None = None
    recurso_id: Nome | None = None


def alteracoes_enviadas(dados):
    alteracoes = dados.model_dump(exclude_none=True)
    if not alteracoes:
        raise HTTPException(400, "Informe pelo menos um campo para alterar.")
    return alteracoes


@router.post("/login")
def login(dados: Login, request: Request, response: Response, sessao: Session = Depends(abrir_sessao)):
    response.headers["Cache-Control"] = "no-store"
    origem = request.client.host if request.client else "desconhecida"
    return acessos.fazer_login(sessao, dados.usuario, dados.senha, origem)


@router.post("/logout")
def logout(identidade=Depends(acessos.obter_sessao_autenticada), sessao: Session = Depends(abrir_sessao)):
    sessao_conta, _ = identidade
    sessao.execute(delete(SessaoConta).where(SessaoConta.token_hash == sessao_conta.token_hash))
    sessao.commit()
    return {"status": "sessão encerrada"}


@router.post("/conta/senha", status_code=204, dependencies=[Depends(acessos.obter_conta)])
def trocar_senha(dados: TrocaSenha, credenciais=Depends(acessos.esquema_bearer),
                 sessao: Session = Depends(abrir_sessao)):
    acessos.trocar_senha(sessao, credenciais, dados.senha_atual, dados.nova_senha)


@router.get("/contexto")
def contexto_atual(contexto: acessos.Contexto = Depends(acessos.obter_contexto)):
    return {
        "usuario": acessos.usuario_json(contexto.conta) if contexto.conta else None,
        "empresa": acessos.vinculo_json(contexto.empresa, contexto.papel, contexto.permissoes),
    }


@router.get("/empresas")
def listar_empresas(_=Depends(acessos.exigir_plataforma), sessao: Session = Depends(abrir_sessao)):
    return [acessos.empresa_json(empresa) for empresa in sessao.scalars(select(Empresa).order_by(Empresa.nome))]


@router.post("/empresas", status_code=201)
def criar_empresa(dados: DadosEmpresa, autor=Depends(acessos.exigir_plataforma),
                  sessao: Session = Depends(abrir_sessao)):
    empresa = Empresa(nome=dados.nome)
    sessao.add(empresa)
    try:
        sessao.flush()
    except IntegrityError as erro:
        sessao.rollback()
        raise HTTPException(409, "Já existe uma empresa com este nome.") from erro
    acessos.registrar_evento(sessao, empresa.id, autor.id, "criar_empresa", nome=empresa.nome)
    sessao.commit()
    return acessos.empresa_json(empresa)


@router.patch("/empresas/{empresa_id}")
def alterar_empresa(empresa_id: Identificador, dados: AlteracaoEmpresa, autor=Depends(acessos.exigir_plataforma),
                    sessao: Session = Depends(abrir_sessao)):
    empresa = acessos.bloquear_empresa(sessao, empresa_id)
    anterior = acessos.empresa_json(empresa)
    for campo, valor in alteracoes_enviadas(dados).items():
        setattr(empresa, campo, valor)
    acessos.registrar_evento(sessao, empresa.id, autor.id, "alterar_empresa", anterior=anterior,
                             atual=acessos.empresa_json(empresa))
    acessos.gravar(sessao, "Já existe uma empresa com este nome.")
    return acessos.empresa_json(empresa)


@router.post("/empresas/{empresa_id}/convites", status_code=201)
def convidar_primeiro_administrador(empresa_id: Identificador, dados: ConviteAdministrador, response: Response,
                                  autor=Depends(acessos.exigir_plataforma), sessao: Session = Depends(abrir_sessao)):
    empresa = acessos.bloquear_empresa(sessao, empresa_id)
    if not empresa.ativo or acessos.tem_administrador(sessao, empresa.id):
        raise HTTPException(409, "A empresa precisa estar ativa e sem administrador para emitir este convite.")
    response.headers["Cache-Control"] = "no-store"
    return acessos.emitir_convite(sessao, empresa, autor, dados.email, acessos.ADMINISTRADOR, primeiro_administrador=True)


@router.get("/equipe")
def equipe(contexto: acessos.Contexto = Depends(acessos.obter_contexto), sessao: Session = Depends(abrir_sessao)):
    return acessos.listar_equipe(sessao, contexto)


@router.patch("/equipe/{conta_id}")
def alterar_membro(conta_id: Identificador, dados: AlteracaoVinculo,
                   contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                   sessao: Session = Depends(abrir_sessao)):
    return acessos.alterar_membro(sessao, contexto, conta_id, alteracoes_enviadas(dados))


@router.get("/equipe/convites")
def listar_convites(contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                    sessao: Session = Depends(abrir_sessao)):
    acessos.exigir(contexto, "administrar")
    consulta = select(ConviteConta).where(ConviteConta.empresa_id == contexto.empresa.id).order_by(ConviteConta.id.desc())
    return [acessos.convite_json(convite) for convite in sessao.scalars(consulta)]


@router.post("/equipe/convites", status_code=201)
def convidar_membro(dados: Convite, response: Response, contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                    sessao: Session = Depends(abrir_sessao)):
    empresa = acessos.bloquear_administracao(sessao, contexto)
    response.headers["Cache-Control"] = "no-store"
    return acessos.emitir_convite(sessao, empresa, contexto.conta, dados.email, dados.papel)


@router.delete("/equipe/convites/{convite_id}", status_code=204)
def revogar_convite(convite_id: Identificador, contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                   sessao: Session = Depends(abrir_sessao)):
    empresa = acessos.bloquear_administracao(sessao, contexto)
    convite = sessao.scalar(select(ConviteConta).where(ConviteConta.id == convite_id,
                                                     ConviteConta.empresa_id == empresa.id))
    if convite is None:
        raise HTTPException(404, "Convite não encontrado nesta empresa.")
    if convite.usado_em is not None:
        raise HTTPException(409, "O convite foi aceito. Altere o vínculo para gerenciar o acesso.")
    if convite.revogado_em is None:
        convite.revogado_em = agora_utc()
        acessos.registrar_evento(sessao, empresa.id, contexto.conta.id, "revogar_convite", convite_id=convite.id)
        sessao.commit()


@router.post("/convites/aceitar", status_code=201)
def aceitar_convite(dados: Aceite, credenciais=Depends(acessos.esquema_bearer), sessao: Session = Depends(abrir_sessao)):
    return acessos.aceitar_convite(sessao, dados.token, dados.email, dados.nome, dados.senha, credenciais)


@router.get("/equipe/eventos")
def listar_eventos(contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                  sessao: Session = Depends(abrir_sessao)):
    acessos.exigir(contexto, "administrar")
    consulta = (select(EventoAcesso).where(EventoAcesso.empresa_id == contexto.empresa.id)
                .order_by(EventoAcesso.id.desc()).limit(100))
    return [{"id": evento.id, "autor_id": evento.autor_id, "acao": evento.acao, "dados": evento.dados,
             "registrado_em": formatar_utc(evento.registrado_em)} for evento in sessao.scalars(consulta)]


@router.get("/papeis")
def listar_papeis(contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                  sessao: Session = Depends(abrir_sessao)):
    acessos.exigir(contexto, "administrar")
    return [acessos.papel_json(sessao, contexto.empresa.id, papel) for papel in acessos.PAPEIS]


@router.patch("/papeis/{papel}")
def alterar_papel(papel: Papel, dados: AlteracaoPapel, contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                  sessao: Session = Depends(abrir_sessao)):
    return acessos.alterar_permissoes_do_papel(sessao, contexto, papel, dados.permissoes)


@router.get("/integracoes")
def listar_integracoes(contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                       sessao: Session = Depends(abrir_sessao)):
    acessos.exigir(contexto, "administrar")
    consulta = select(Integracao).where(Integracao.empresa_id == contexto.empresa.id).order_by(Integracao.id)
    return [acessos.integracao_json(integracao) for integracao in sessao.scalars(consulta)]


@router.post("/integracoes", status_code=201)
def criar_integracao(dados: DadosIntegracao, response: Response,
                     contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                     sessao: Session = Depends(abrir_sessao)):
    response.headers["Cache-Control"] = "no-store"
    return acessos.criar_integracao(sessao, contexto, dados)


@router.delete("/integracoes/{integracao_id}", status_code=204)
def revogar_integracao(integracao_id: Identificador, contexto: acessos.Contexto = Depends(acessos.obter_contexto),
                      sessao: Session = Depends(abrir_sessao)):
    acessos.revogar_integracao(sessao, contexto, integracao_id)
