"""
Formato dos JSON que a API recebe (validados pelo Pydantic).

Regras que envolvem dois campos ao mesmo tempo (minimo menor que maximo)
ficam em services/frutas.py, na funcao validar_faixa.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class FaixaSegura(BaseModel):
    temp_min_c: float
    temp_max_c: float
    umidade_min_pct: float = Field(ge=0, le=100)
    umidade_max_pct: float = Field(ge=0, le=100)


class FrutaDados(FaixaSegura):
    """Campos de uma fruta que podem ser editados (usado no PUT)."""
    nome: str = Field(min_length=1)
    fonte: str = Field(min_length=1)


class FrutaNova(FrutaDados):
    """Os mesmos campos, mais o id, que so e escolhido no cadastro."""
    # Letras minusculas sem acento, numeros, hifen ou sublinhado. Ex.: "uva"
    id: str = Field(pattern=r"^[a-z0-9_-]+$")


class LoteNovo(BaseModel):
    fruta: str
    origem: str = Field(min_length=1)
    porto_destino: str = Field(min_length=1)
    inicio: datetime | None = None
    faixa_segura: FaixaSegura | None = None


class Encerramento(BaseModel):
    fim: datetime | None = None
