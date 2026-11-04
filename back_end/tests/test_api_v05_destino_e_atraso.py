"""
Testes das novidades da v0.5 da API (docs/api-contrato.md): destino do lote
(porto ou mercado interno), faixa da uva e leituras que chegam atrasadas.
"""

from auxiliares import (
    analise_do_lote,
    buscar_fruta,
    corpo_de_lote,
    criar_lote,
    detalhe_do_lote,
    em_utc,
    encerrar_lote,
    leitura_do_thingspeak,
    leituras_do_thingspeak,
    sem_campo,
    thingspeak_devolve,
)


# ---------- destino: porto ou mercado interno ----------

def test_lote_para_o_mercado_interno(cliente):
    lote = criar_lote(cliente, destino="Ceasa Recife", tipo_destino="mercado_interno")
    detalhe = detalhe_do_lote(cliente, lote)
    assert detalhe["destino"] == "Ceasa Recife"
    assert detalhe["tipo_destino"] == "mercado_interno"


def test_lote_para_o_porto(cliente):
    lote = criar_lote(cliente)
    assert lote["destino"] == "Porto de Suape"
    assert lote["tipo_destino"] == "porto"


def test_campo_antigo_porto_destino_nao_existe_mais(cliente):
    lote = criar_lote(cliente)
    assert "porto_destino" not in lote
    assert "porto_destino" not in detalhe_do_lote(cliente, lote)


def test_tipo_de_destino_invalido_devolve_400(cliente):
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(tipo_destino="aeroporto"))
    assert resposta.status_code == 400
    assert resposta.json() == {
        "erro": "tipo_destino precisa ser 'porto' ou 'mercado_interno'."
    }


def test_lote_sem_tipo_de_destino_devolve_400(cliente):
    corpo = sem_campo(corpo_de_lote(), "tipo_destino")
    resposta = cliente.post("/api/lotes", json=corpo)
    assert resposta.status_code == 400
    assert resposta.json() == {"erro": "tipo_destino: campo obrigatório"}


# ---------- faixa da uva decidida: 0 a 2 °C (Embrapa) ----------

def test_faixa_inicial_da_uva_e_0_a_2_graus_com_fonte_da_embrapa(cliente):
    uva = buscar_fruta(cliente, "uva")
    assert uva["temp_min_c"] == 0.0
    assert uva["temp_max_c"] == 2.0
    assert "Embrapa" in uva["fonte"]


# ---------- leituras atrasadas ----------

def test_leituras_que_chegam_depois_do_encerramento_entram_no_lote(cliente, monkeypatch):
    # O sensor ficou sem sinal: o lote foi encerrado antes de as leituras chegarem.
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T20:00:00Z")

    # Elas chegam depois, em lote, com o horario da medicao (dentro do lote).
    # 3 graus acima do teto (2) por 10 h = 30 graus-hora
    thingspeak_devolve(monkeypatch, leituras_do_thingspeak(range(0, 11), 5.0))
    cliente.post("/api/sincronizar")

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 11
    assert analise["graus_hora_acima"] == 30.0


def test_leituras_atrasadas_com_horario_depois_do_fim_nao_entram(cliente, monkeypatch):
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T12:00:00Z")

    # Uma leitura dentro do lote (09:00) e uma medida depois do fim (13:00).
    leituras = [
        leitura_do_thingspeak(1, em_utc(0), 1.0),
        leitura_do_thingspeak(2, em_utc(4), 1.0),
    ]
    thingspeak_devolve(monkeypatch, leituras)
    cliente.post("/api/sincronizar")

    assert analise_do_lote(cliente, lote)["amostras"] == 1


def test_leituras_fora_de_ordem_dao_o_mesmo_resultado(cliente, monkeypatch):
    lote = criar_lote(cliente)

    # Primeiro chegam as ultimas horas da viagem...
    thingspeak_devolve(monkeypatch, leituras_do_thingspeak(range(6, 11), 5.0))
    cliente.post("/api/sincronizar")

    # ...e so depois as primeiras, que estavam guardadas no sensor.
    thingspeak_devolve(monkeypatch, leituras_do_thingspeak(range(0, 6), 5.0))
    cliente.post("/api/sincronizar")

    # Mesma conta de quem recebeu tudo em ordem: 3 graus acima por 10 h = 30
    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 11
    assert analise["graus_hora_acima"] == 30.0
    assert analise["primeira_leitura"] == "2026-10-24T09:00:00Z"
