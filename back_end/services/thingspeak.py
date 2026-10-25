"""
Leitura dos feeds do canal publico do ThingSpeak.

Mapeamento dos campos (README.md):
    field1 = temperatura (C), field2 = umidade relativa (%),
    field5 = luminosidade (lux)
"""

from datetime import datetime

import requests

URL_FEEDS = "https://api.thingspeak.com/channels/{canal}/feeds.json"


class ErroThingSpeak(Exception):
    """O ThingSpeak nao respondeu ou respondeu com erro."""


def converter_numero(valor):
    """O ThingSpeak manda os campos como texto; campo vazio vira None."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def converter_data(texto):
    # Ex.: "2026-09-29T22:32:34Z" (sempre em UTC)
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def converter_feed(feed):
    """Transforma uma entrada do ThingSpeak em uma leitura do PlantSync."""
    return {
        "entry_id": feed["entry_id"],
        "data_hora": converter_data(feed["created_at"]),
        "temperatura_c": converter_numero(feed.get("field1")),
        "umidade_pct": converter_numero(feed.get("field2")),
        "luminosidade_lux": converter_numero(feed.get("field5")),
    }


def buscar_leituras(canal, quantidade=8000, read_api_key=None):
    """
    Busca as ultimas leituras do canal. 8000 e o maximo que o
    ThingSpeak devolve por chamada. A chave so e preciso se o canal
    for privado; ela vem da configuracao, nunca do codigo.
    """
    parametros = {"results": quantidade}
    if read_api_key:
        parametros["api_key"] = read_api_key

    try:
        resposta = requests.get(URL_FEEDS.format(canal=canal), params=parametros, timeout=15)
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError) as erro:
        raise ErroThingSpeak(f"Falha ao consultar o ThingSpeak: {erro}") from erro

    return [converter_feed(feed) for feed in dados.get("feeds", [])]
