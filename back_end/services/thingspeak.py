"""
Leitura dos feeds do canal publico do ThingSpeak.

Mapeamento dos campos (README.md):
    field1 = temperatura (C), field2 = umidade relativa (%),
    field5 = luminosidade (lux)
"""

from datetime import datetime, timedelta, timezone

import requests

from services.datas import formatar_para_thingspeak
from services.erros import ErroThingSpeak

URL_FEEDS = "https://api.thingspeak.com/channels/{canal}/feeds.json"
LIMITE_POR_CONSULTA = 8000
MAXIMO_DE_CONSULTAS = 100
MENSAGEM_DE_ERRO = (
    "Não foi possível ler os dados do ThingSpeak agora. Tente de novo em alguns minutos."
)


def converter_numero(valor):
    """O ThingSpeak manda os campos como texto; campo vazio vira None."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def converter_data(texto):
    # Ex.: "2026-09-29T22:32:34Z" (sempre em UTC)
    data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data


def converter_feed(feed):
    """Transforma uma entrada do ThingSpeak em uma leitura do PlantSync."""
    if not isinstance(feed, dict):
        raise ValueError(f"entrada invalida: {feed}")
    entry_id = feed.get("entry_id")
    created_at = feed.get("created_at")
    if not isinstance(entry_id, int) or not isinstance(created_at, str):
        raise ValueError(f"entrada invalida: {feed}")

    return {
        "entry_id": entry_id,
        "data_hora": converter_data(created_at),
        "temperatura_c": converter_numero(feed.get("field1")),
        "umidade_pct": converter_numero(feed.get("field2")),
        "luminosidade_lux": converter_numero(feed.get("field5")),
    }


def buscar_pagina(canal, parametros):
    """
    Faz uma consulta ao canal. Qualquer resposta fora do formato esperado (corpo
    que nao e objeto, entrada sem data ou sem entry_id) vira ErroThingSpeak.
    """
    try:
        resposta = requests.get(URL_FEEDS.format(canal=canal), params=parametros, timeout=15)
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict) or not isinstance(dados.get("feeds"), list):
            raise ValueError(f"corpo inesperado: {dados}")

        leituras = []
        for feed in dados["feeds"]:
            leituras.append(converter_feed(feed))
        return leituras
    except (requests.RequestException, ValueError) as erro:
        # O detalhe tecnico (em ingles) fica guardado no "from erro";
        # quem usa o painel ve so a mensagem em portugues.
        raise ErroThingSpeak(MENSAGEM_DE_ERRO) from erro


def buscar_leituras(canal, desde=None, chave_leitura=None):
    """
    Busca as leituras do canal a partir de 'desde' (ou todas, se for None).

    Cada consulta devolve no maximo as 8000 leituras mais recentes, cerca de
    44 h a uma leitura a cada 20 s. Por isso, enquanto a consulta vier cheia,
    pedimos as anteriores a mais antiga recebida. A chave so e preciso se o
    canal for privado; ela vem da configuracao, nunca do codigo.
    """
    parametros = {"results": LIMITE_POR_CONSULTA}
    if chave_leitura:
        parametros["api_key"] = chave_leitura
    if desde is not None:
        parametros["start"] = formatar_para_thingspeak(desde)

    leituras = []
    # Limite de consultas para nao ficar em laco se o servico ignorar o "end".
    for _ in range(MAXIMO_DE_CONSULTAS):
        pagina = buscar_pagina(canal, parametros)
        leituras.extend(pagina)
        if len(pagina) < LIMITE_POR_CONSULTA:
            return leituras

        datas = [leitura["data_hora"] for leitura in pagina]
        parametros["end"] = formatar_para_thingspeak(min(datas) - timedelta(seconds=1))

    raise ErroThingSpeak(MENSAGEM_DE_ERRO)
