"""
Laudo do lote por QR Code: uma visao publica e uma visao completa.

- Visao publica (consumidor): aberta pelo codigo_publico do QR Code.
  So mostra fruta, produtor, origem e o selo. Nunca mostra temperaturas.
- Laudo completo (produtor e importador): aberto pelo token_laudo, um
  segredo enviado em particular. Funciona como a chave de um documento
  compartilhado: o produtor e o importador nao tem login no painel.
"""

from models.tabelas import Fruta, Lote
from services.analise import analisar_lote, limpar_leituras, maior_buraco_em_minutos
from services.erros import ErroNaoEncontrado
from services.lotes import (
    analise_para_json,
    buscar_e_analisar,
    faixa_do_lote,
    leituras_do_lote,
    leituras_para_grafico,
    lote_basico_json,
)

# A mesma mensagem para codigo e token, para nao dar pistas de quais existem.
MENSAGEM_NAO_ENCONTRADO = "Código não encontrado."

# O selo precisa de dados suficientes para afirmar algo sobre a viagem. Valores
# escolhidos pela equipe, a validar com produtor (ver docs/api-contrato.md):
# 10 leituras sao cerca de 3 min de envio normal (uma a cada 20 s), e 30 min
# sem leitura ja escondem uma parada com a porta aberta.
MINIMO_LEITURAS_SELO = 10
MAIOR_BURACO_SELO_MIN = 30


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


def tem_selo(lote, analise, leituras):
    """
    O selo "transportado dentro da faixa segura" so aparece se o lote ja
    chegou, tem leituras suficientes, sem buraco grande na viagem, e ficou
    VERDE no calor e no frio. Leituras atrasadas contam assim que chegam.
    """
    if lote.fim is None:
        return False
    if len(leituras) < MINIMO_LEITURAS_SELO:
        return False
    if maior_buraco_em_minutos(leituras, lote.inicio, lote.fim) > MAIOR_BURACO_SELO_MIN:
        return False
    return analise["nivel_acima"] == "VERDE" and analise["nivel_abaixo"] == "VERDE"


def visao_publica_json(sessao, lote):
    """O que o consumidor ve. Nada de curva, temperatura ou nivel de risco."""
    fruta = sessao.get(Fruta, lote.fruta_id)
    leituras = limpar_leituras(leituras_do_lote(sessao, lote))
    analise = analisar_lote(leituras, faixa_do_lote(lote))
    return {
        "fruta": fruta.nome,
        "produtor": lote.produtor,
        "origem": lote.origem,
        "selo_faixa_segura": tem_selo(lote, analise, leituras),
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
