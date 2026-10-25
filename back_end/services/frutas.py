"""Regras das frutas e de suas faixas seguras."""

from models.tabelas import Fruta

# Valores gravados na primeira execucao. Todos podem ser editados pela API.
# Fontes completas em docs/api-contrato.md, secao Referencias.
FRUTAS_INICIAIS = [
    {
        "id": "uva",
        "nome": "Uva de mesa",
        "temp_min_c": 0.0,
        "temp_max_c": 2.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 95.0,
        "fonte": "Embrapa Semiárido, Cultivo da videira (Lima, 2016)",
    },
    {
        "id": "manga",
        "nome": "Manga",
        "temp_min_c": 10.0,
        "temp_max_c": 13.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 90.0,
        "fonte": "USDA, Agriculture Handbook 66 (Paull e Chen, 2016); "
                 "Embrapa Semiárido, Cultivo da mangueira (Assis, 2015)",
    },
]


def cadastrar_frutas_iniciais(sessao):
    """Grava as frutas iniciais se a tabela ainda estiver vazia."""
    if sessao.query(Fruta).count() > 0:
        return
    for dados in FRUTAS_INICIAIS:
        sessao.add(Fruta(**dados))
    sessao.commit()


def validar_faixa(faixa):
    """Devolve a mensagem de erro da faixa, ou None se estiver tudo certo."""
    if faixa.temp_min_c >= faixa.temp_max_c:
        return "temp_min_c precisa ser menor que temp_max_c."
    if faixa.umidade_min_pct >= faixa.umidade_max_pct:
        return "umidade_min_pct precisa ser menor que umidade_max_pct."
    return None


def fruta_para_json(fruta):
    return {
        "id": fruta.id,
        "nome": fruta.nome,
        "temp_min_c": fruta.temp_min_c,
        "temp_max_c": fruta.temp_max_c,
        "umidade_min_pct": fruta.umidade_min_pct,
        "umidade_max_pct": fruta.umidade_max_pct,
        "fonte": fruta.fonte,
    }
