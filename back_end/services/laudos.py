"""
Laudo do lote por QR Code: uma visao publica e uma visao completa.

- Visao publica (consumidor): aberta pelo codigo_publico do QR Code.
  So mostra fruta, produtor, origem e o selo. Nunca mostra temperaturas.
- Laudo completo (produtor e importador): aberto pelo token_laudo, um
  segredo enviado em particular. Funciona como a chave de um documento
  compartilhado, ja que o login com perfis (RF07) ainda nao foi decidido.
"""

from models.tabelas import Fruta, Lote
from services.erros import ErroNaoEncontrado
from services.lotes import (
    analise_para_json,
    buscar_e_analisar,
    leituras_para_grafico,
    lote_basico_json,
)

# A mesma mensagem para codigo e token, para nao dar pistas de quais existem.
MENSAGEM_NAO_ENCONTRADO = "Código não encontrado."


def buscar_por_codigo_publico(sessao, codigo):
    lote = sessao.query(Lote).filter(Lote.codigo_publico == codigo).first()
    if lote is None:
        raise ErroNaoEncontrado(MENSAGEM_NAO_ENCONTRADO)
    return lote


def buscar_por_token(sessao, token):
    lote = sessao.query(Lote).filter(Lote.token_laudo == token).first()
    if lote is None:
        raise ErroNaoEncontrado(MENSAGEM_NAO_ENCONTRADO)
    return lote


def tem_selo(lote, analise):
    """
    O selo "transportado dentro da faixa segura" so aparece se o lote ja
    chegou, tem leituras e ficou VERDE no calor e no frio.
    """
    if lote.fim is None:
        return False
    if analise["amostras"] == 0:
        return False
    return analise["nivel_acima"] == "VERDE" and analise["nivel_abaixo"] == "VERDE"


def visao_publica_json(sessao, lote):
    """O que o consumidor ve. Nada de curva, temperatura ou nivel de risco."""
    fruta = sessao.get(Fruta, lote.fruta_id)
    analise = buscar_e_analisar(sessao, lote)
    return {
        "fruta": fruta.nome,
        "produtor": lote.produtor,
        "origem": lote.origem,
        "selo_faixa_segura": tem_selo(lote, analise),
    }


def laudo_completo_json(sessao, lote):
    """
    O laudo do produtor e do importador: lote, analise e a curva da viagem.
    Nao devolve o token_laudo: quem abriu o laudo ja o tem.
    """
    laudo = lote_basico_json(lote)
    laudo["analise"] = analise_para_json(buscar_e_analisar(sessao, lote))
    laudo["leituras"] = leituras_para_grafico(sessao, lote)
    return laudo
