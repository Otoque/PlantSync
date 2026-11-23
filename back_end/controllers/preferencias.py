"""Preferências individuais e identidade da organização atual."""

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.preferencias import PreferenciaConta
from services import acessos

router = APIRouter(prefix="/api/v1", tags=["preferências"])
Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class Perfil(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Nome | None = None
    fuso: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    idioma: Literal["pt-BR"] | None = None
    avisos_conservacao: bool | None = None


class IdentidadeEmpresa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Nome


def perfil_json(conta, perfil):
    return {
        "id": conta.id,
        "nome": perfil.nome if perfil else conta.nome,
        "email": conta.email,
        "fuso": perfil.fuso if perfil else "America/Sao_Paulo",
        "idioma": perfil.idioma if perfil else "pt-BR",
        "avisos_conservacao": perfil.avisos_conservacao if perfil else True,
    }


@router.get("/perfil")
def consultar_perfil(conta=Depends(acessos.obter_conta), sessao: Session = Depends(abrir_sessao)):
    return perfil_json(conta, sessao.get(PreferenciaConta, conta.id))


@router.patch("/perfil")
def alterar_perfil(dados: Perfil, conta=Depends(acessos.obter_conta),
                   sessao: Session = Depends(abrir_sessao)):
    alteracoes = dados.model_dump(exclude_none=True)
    if not alteracoes:
        raise HTTPException(400, "Informe uma preferência para alterar.")
    if dados.fuso:
        try:
            ZoneInfo(dados.fuso)
        except (ZoneInfoNotFoundError, ValueError) as erro:
            raise HTTPException(400, "Fuso horário inválido ou indisponível.") from erro
    perfil = sessao.get(PreferenciaConta, conta.id)
    if perfil is None:
        perfil = PreferenciaConta(conta_id=conta.id, nome=conta.nome)
        sessao.add(perfil)
    for campo, valor in alteracoes.items():
        setattr(perfil, campo, valor)
    sessao.commit()
    return perfil_json(conta, perfil)


@router.get("/configuracoes/empresa")
def consultar_empresa(contexto=Depends(acessos.obter_contexto)):
    acessos.exigir(contexto, "administrar")
    return acessos.empresa_json(contexto.empresa)


@router.patch("/configuracoes/empresa")
def alterar_empresa(dados: IdentidadeEmpresa, contexto=Depends(acessos.obter_contexto),
                   sessao: Session = Depends(abrir_sessao)):
    empresa = acessos.bloquear_administracao(sessao, contexto)
    anterior = empresa.nome
    empresa.nome = dados.nome
    acessos.registrar_evento(
        sessao, empresa.id, contexto.conta.id, "alterar_identidade_empresa",
        anterior=anterior, atual=dados.nome,
    )
    try:
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        raise HTTPException(409, "Já existe uma empresa com este nome.") from erro
    return acessos.empresa_json(empresa)
