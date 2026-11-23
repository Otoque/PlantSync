"""Catálogo de conservação administrado no contexto da empresa."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.limites import TEMP_FISICA_MAX, TEMP_FISICA_MIN
from services import catalogo
from services.acessos import Contexto, exigir, obter_contexto
from services.operacao_acesso import exigir_escopo

router = APIRouter(prefix="/api/v1", tags=["catálogo de conservação"])
Temperatura = Annotated[float, Field(ge=TEMP_FISICA_MIN, le=TEMP_FISICA_MAX)]
Umidade = Annotated[float, Field(ge=0, le=100)]
Texto = Annotated[str, Field(min_length=1, max_length=240)]


class CriarFruta(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    nome: Texto
    temp_min_c: Temperatura
    temp_max_c: Temperatura
    umidade_min_pct: Umidade
    umidade_max_pct: Umidade
    risco_no_frio: Texto | None = None
    fonte: Texto


class EditarFruta(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    version: int = Field(ge=0)
    nome: Texto | None = None
    temp_min_c: Temperatura | None = None
    temp_max_c: Temperatura | None = None
    umidade_min_pct: Umidade | None = None
    umidade_max_pct: Umidade | None = None
    risco_no_frio: Texto | None = None
    fonte: Texto | None = None


@router.get("/frutas")
def listar(sessao: Session = Depends(abrir_sessao), contexto: Contexto = Depends(obter_contexto)):
    exigir(contexto, "consultar")
    exigir_escopo(contexto, "catalogo")
    return catalogo.listar_frutas(sessao, contexto.empresa.id)


@router.post("/frutas", status_code=201)
def criar(dados: CriarFruta, sessao: Session = Depends(abrir_sessao),
          contexto: Contexto = Depends(obter_contexto)):
    return catalogo.criar_fruta(sessao, contexto, dados.model_dump())


@router.patch("/frutas/{fruta_id}")
def editar(fruta_id: str, dados: EditarFruta, sessao: Session = Depends(abrir_sessao),
           contexto: Contexto = Depends(obter_contexto)):
    valores = dados.model_dump(exclude_unset=True)
    valores = {campo: valor for campo, valor in valores.items() if valor is not None or campo == "risco_no_frio"}
    return catalogo.alterar_fruta(sessao, contexto, fruta_id, valores)
