"""
Constantes e funcoes auxiliares usadas pelos testes da API
(test_api_frutas_lotes.py e test_api_alertas_sincronizacao.py).

Os testes importam com "from auxiliares import ..." porque o pytest
coloca a pasta tests/ no caminho de importacao.
"""

from datetime import datetime, timedelta, timezone

from models.tabelas import Leitura

INICIO = datetime(2026, 10, 24, 9, 0, 0)  # 24/10/2026 09:00 UTC

LOTE_UVA = {
    "fruta": "uva",
    "origem": "Packing house Petrolina",
    "porto_destino": "Suape",
    "inicio": "2026-10-24T09:00:00Z",
}

FAIXA_UVA = {
    "temp_min_c": 0.0,
    "temp_max_c": 2.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 95.0,
}

FORMATO_DATA = "%Y-%m-%dT%H:%M:%SZ"


# ---------- dicionarios de entrada ----------

def sem_campo(corpo, nome):
    """Devolve uma copia do dicionario sem a chave 'nome'."""
    copia = dict(corpo)
    del copia[nome]
    return copia


def fruta_melao(**mudancas):
    """Corpo de uma fruta nova valida (melao); 'mudancas' troca alguns campos."""
    corpo = {
        "id": "melao",
        "nome": "Melão",
        "temp_min_c": 2.0,
        "temp_max_c": 5.0,
        "umidade_min_pct": 90.0,
        "umidade_max_pct": 95.0,
        "fonte": "Referência da faixa",
    }
    corpo.update(mudancas)
    return corpo


def corpo_de_lote(**mudancas):
    """Corpo de um lote de uva valido; 'mudancas' troca ou acrescenta campos."""
    corpo = dict(LOTE_UVA)
    corpo.update(mudancas)
    return corpo


def faixa_da_uva(**mudancas):
    """Faixa segura da uva; 'mudancas' troca alguns limites."""
    faixa = dict(FAIXA_UVA)
    faixa.update(mudancas)
    return faixa


# ---------- chamadas a API ----------

def cadastrar_fruta(cliente, **mudancas):
    """Cadastra o melao (com 'mudancas') e devolve a resposta, seja qual for o status."""
    return cliente.post("/api/frutas", json=fruta_melao(**mudancas))


def editar_fruta(cliente, id_da_fruta, **mudancas):
    """Edita a fruta com os dados do melao (sem o id) alterados por 'mudancas'."""
    corpo = sem_campo(fruta_melao(**mudancas), "id")
    return cliente.put(f"/api/frutas/{id_da_fruta}", json=corpo)


def buscar_fruta(cliente, id_da_fruta):
    """Procura uma fruta na lista de GET /api/frutas e devolve o dicionario dela."""
    for fruta in cliente.get("/api/frutas").json():
        if fruta["id"] == id_da_fruta:
            return fruta
    raise AssertionError(f"fruta {id_da_fruta} nao esta na lista")


def criar_lote(cliente, **mudancas):
    """Cria um lote de uva (com 'mudancas') e devolve o JSON; exige status 201."""
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(**mudancas))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def encerrar_lote(cliente, lote, fim=None):
    """Encerra o lote e devolve a resposta. Sem 'fim', nao envia corpo."""
    endereco = f"/api/lotes/{lote['id']}/encerrar"
    if fim is None:
        return cliente.post(endereco)
    return cliente.post(endereco, json={"fim": fim})


def detalhe_do_lote(cliente, lote):
    """Devolve o JSON de GET /api/lotes/<id>."""
    return cliente.get(f"/api/lotes/{lote['id']}").json()


def analise_do_lote(cliente, lote):
    """Devolve so o campo 'analise' do detalhe do lote."""
    return detalhe_do_lote(cliente, lote)["analise"]


def leituras_do_lote(cliente, lote):
    """Devolve o JSON de GET /api/lotes/<id>/leituras."""
    return cliente.get(f"/api/lotes/{lote['id']}/leituras").json()


# ---------- leituras no banco ----------

def em(horas, minutos=0, segundos=0):
    """Horario a 'horas' do inicio do lote (09:00 UTC de 24/10), sem fuso, como o banco guarda."""
    return INICIO + timedelta(hours=horas, minutes=minutos, seconds=segundos)


def em_utc(horas, minutos=0, segundos=0):
    """Igual a em(), mas com fuso UTC, como o ThingSpeak entrega."""
    return em(horas, minutos, segundos).replace(tzinfo=timezone.utc)


def nova_leitura(data_hora, temperatura, umidade=90.0, lux=None):
    """Dados de uma leitura para gravar no banco."""
    return {
        "data_hora": data_hora,
        "temperatura_c": temperatura,
        "umidade_pct": umidade,
        "luminosidade_lux": lux,
    }


def leituras_por_hora(temperatura, horas=10, horas_com_porta_aberta=()):
    """Uma leitura por hora, da hora 0 ate 'horas', sempre na mesma temperatura."""
    leituras = []
    for hora in range(0, horas + 1):
        lux = None
        if hora in horas_com_porta_aberta:
            lux = 640.0  # acima de 300 lux = porta aberta
        leituras.append(nova_leitura(em(hora), temperatura, lux=lux))
    return leituras


def gravar_leituras(banco, leituras):
    """Grava leituras (de nova_leitura) direto no banco de teste, o mesmo que a API usa."""
    with banco() as sessao:
        for numero, dados in enumerate(leituras, start=1):
            sessao.add(Leitura(
                entry_id=numero,
                data_hora=dados["data_hora"],
                temperatura_c=dados["temperatura_c"],
                umidade_pct=dados["umidade_pct"],
                luminosidade_lux=dados["luminosidade_lux"],
            ))
        sessao.commit()


# ---------- datas ----------

def agora_utc():
    """Horario atual em UTC, sem fuso (para comparar com as datas da API)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ler_data(texto):
    """Converte 'AAAA-MM-DDTHH:MM:SSZ' em datetime; da erro se o formato for outro."""
    return datetime.strptime(texto, FORMATO_DATA)


def conferir_data_utc(texto):
    """Confere que a data termina em Z e e ISO 8601 sem fracao de segundo."""
    assert texto.endswith("Z"), texto
    ler_data(texto)
