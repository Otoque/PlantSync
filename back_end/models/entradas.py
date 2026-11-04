"""
Formato dos JSON que a API recebe (validados pelo Pydantic).

Regras que envolvem dois campos ao mesmo tempo (minimo menor que maximo)
ficam em services/frutas.py, na funcao validar_faixa.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from models.limites import TEMP_FISICA_MAX, TEMP_FISICA_MIN


class FaixaSegura(BaseModel):
    # allow_inf_nan=False recusa Infinity e NaN, que o JSON do Python aceita
    # mas que quebrariam as respostas da API se fossem gravados no banco.
    temp_min_c: float = Field(ge=TEMP_FISICA_MIN, le=TEMP_FISICA_MAX, allow_inf_nan=False)
    temp_max_c: float = Field(ge=TEMP_FISICA_MIN, le=TEMP_FISICA_MAX, allow_inf_nan=False)
    umidade_min_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    umidade_max_pct: float = Field(ge=0, le=100, allow_inf_nan=False)


class FrutaDados(FaixaSegura):
    """Campos de uma fruta que podem ser editados (usado no PUT)."""
    nome: str = Field(min_length=1)
    fonte: str = Field(min_length=1)
    risco_no_frio: str | None = None


class FrutaNova(FrutaDados):
    """Os mesmos campos, mais o id, que so e escolhido no cadastro."""
    # Letras minusculas sem acento, numeros, hifen ou sublinhado. Ex.: "uva"
    id: str = Field(pattern=r"^[a-z0-9_-]+$")


class LoteNovo(BaseModel):
    fruta: str
    produtor: str = Field(min_length=1)
    origem: str = Field(min_length=1)
    destino: str = Field(min_length=1)
    # "porto" ou "mercado_interno"; conferido em services/lotes.py.
    tipo_destino: str
    inicio: datetime | None = None
    faixa_segura: FaixaSegura | None = None


class Encerramento(BaseModel):
    fim: datetime | None = None
