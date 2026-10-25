"""Regras das frutas e de suas faixas seguras."""

from models.tabelas import Fruta
from services.erros import ErroDeRegra, ErroNaoEncontrado

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
    """Levanta ErroDeRegra se o minimo da faixa nao for menor que o maximo."""
    if faixa.temp_min_c >= faixa.temp_max_c:
        raise ErroDeRegra("temp_min_c precisa ser menor que temp_max_c.")
    if faixa.umidade_min_pct >= faixa.umidade_max_pct:
        raise ErroDeRegra("umidade_min_pct precisa ser menor que umidade_max_pct.")


def listar_frutas(sessao):
    return sessao.query(Fruta).order_by(Fruta.id).all()


def buscar_fruta(sessao, fruta_id):
    fruta = sessao.get(Fruta, fruta_id)
    if fruta is None:
        raise ErroNaoEncontrado(f"Fruta '{fruta_id}' não encontrada.")
    return fruta


def criar_fruta(sessao, dados):
    validar_faixa(dados)
    if sessao.get(Fruta, dados.id) is not None:
        raise ErroDeRegra(f"A fruta '{dados.id}' já existe.")

    fruta = Fruta(**dados.model_dump())
    sessao.add(fruta)
    sessao.commit()
    return fruta


def atualizar_fruta(sessao, fruta_id, dados):
    """
    Troca nome, fonte e faixa da fruta. Os lotes ja criados nao mudam,
    porque cada lote guarda a propria copia da faixa.
    """
    fruta = buscar_fruta(sessao, fruta_id)
    validar_faixa(dados)

    fruta.nome = dados.nome
    fruta.fonte = dados.fonte
    fruta.temp_min_c = dados.temp_min_c
    fruta.temp_max_c = dados.temp_max_c
    fruta.umidade_min_pct = dados.umidade_min_pct
    fruta.umidade_max_pct = dados.umidade_max_pct
    sessao.commit()
    return fruta


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
