"""
Testes de caixa-preta de GET /api/alertas e POST /api/sincronizar, escritos a
partir de docs/api-contrato.md.

A sincronizacao nunca acessa a internet: a busca no ThingSpeak e trocada
por uma funcao falsa (monkeypatch).

As funcoes auxiliares (criar_lote, gravar_leituras, em...) ficam em auxiliares.py.
"""

from auxiliares import (
    analise_do_lote,
    conferir_data_utc,
    criar_lote,
    em,
    em_utc,
    encerrar_lote,
    gravar_leituras,
    leituras_do_lote,
    leituras_por_hora,
    nova_leitura,
)
from services import thingspeak
from services.thingspeak import ErroThingSpeak


# ---------- funcoes auxiliares deste arquivo ----------

def leitura_do_thingspeak(entry_id, data_hora, temperatura, umidade=90.0, lux=None):
    """Leitura no formato que services.thingspeak.converter_feed devolve."""
    return {
        "entry_id": entry_id,
        "data_hora": data_hora,
        "temperatura_c": temperatura,
        "umidade_pct": umidade,
        "luminosidade_lux": lux,
    }


def thingspeak_devolve(monkeypatch, leituras):
    """Faz a busca no ThingSpeak devolver 'leituras', sem internet."""

    # Funcao falsa no lugar de buscar_leituras: aceita qualquer argumento
    # que a funcao verdadeira receberia (*args, **kwargs) e ignora todos.
    def buscar_falso(*args, **kwargs):
        return list(leituras)

    monkeypatch.setattr(thingspeak, "buscar_leituras", buscar_falso)


def thingspeak_fora_do_ar(monkeypatch):
    """Faz a busca no ThingSpeak falhar, como se o servico estivesse fora do ar."""

    # Funcao falsa no lugar de buscar_leituras: aceita qualquer argumento
    # que a funcao verdadeira receberia (*args, **kwargs) e sempre da erro.
    def buscar_falso(*args, **kwargs):
        raise ErroThingSpeak("Falha ao consultar o ThingSpeak: fora do ar")

    monkeypatch.setattr(thingspeak, "buscar_leituras", buscar_falso)


def alertas_do_tipo(cliente, tipo):
    """Devolve so os alertas de GET /api/alertas com o 'tipo' pedido."""
    alertas = cliente.get("/api/alertas").json()
    return [alerta for alerta in alertas if alerta["tipo"] == tipo]


# ---------- alertas: quando existem ----------

def test_sem_lotes_nao_ha_alertas(cliente):
    resposta = cliente.get("/api/alertas")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_lote_sem_leituras_nao_gera_alerta(cliente):
    criar_lote(cliente)
    assert cliente.get("/api/alertas").json() == []


def test_lote_verde_sem_porta_aberta_nao_gera_alerta(cliente, banco):
    criar_lote(cliente)
    gravar_leituras(banco, leituras_por_hora(1.0))
    assert cliente.get("/api/alertas").json() == []


def test_lote_encerrado_nao_gera_alerta(cliente, banco):
    lote = criar_lote(cliente)
    # 3 °C acima do limite por 10 h e porta aberta: geraria dois alertas se estivesse em transito
    gravar_leituras(banco, leituras_por_hora(5.0, horas_com_porta_aberta=[3, 4]))
    assert len(cliente.get("/api/alertas").json()) == 2

    encerrar_lote(cliente, lote, fim="2026-10-24T20:00:00Z")
    assert cliente.get("/api/alertas").json() == []


# ---------- alertas: risco termico ----------

def test_risco_termico_amarelo_com_mensagem_do_contrato(cliente, banco):
    lote = criar_lote(cliente)
    # 1 °C acima do limite (2 °C) por 6 h = 6 °C·h -> AMARELO (5 a menos de 20)
    gravar_leituras(banco, leituras_por_hora(3.0, horas=6))

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 1
    assert alertas[0]["lote_id"] == lote["id"]
    assert alertas[0]["fruta"] == "uva"
    assert alertas[0]["tipo"] == "risco_termico"
    assert alertas[0]["nivel"] == "AMARELO"
    assert alertas[0]["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 6 °C·h acima de 2 °C: priorizar na expedição."
    )


def test_risco_termico_laranja_com_mensagem_do_contrato(cliente, banco):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h -> LARANJA
    gravar_leituras(banco, leituras_por_hora(5.0))

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["nivel"] == "LARANJA"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 30 °C·h acima de 2 °C: inspecionar antes do embarque."
    )


def test_risco_termico_vermelho_com_mensagem_do_contrato(cliente, banco):
    lote = criar_lote(cliente)
    # 5 °C acima do limite (2 °C) por 10 h = 50 °C·h -> VERMELHO
    gravar_leituras(banco, leituras_por_hora(7.0))

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["nivel"] == "VERMELHO"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 50 °C·h acima de 2 °C: "
        "redirecionar para mercado interno ou processamento."
    )


def test_risco_termico_usa_o_limite_da_fruta_do_lote(cliente, banco):
    lote = criar_lote(cliente, fruta="manga")
    # limite da manga = 13 °C; 2 °C acima por 10 h = 20 °C·h -> LARANJA (20 ja e laranja)
    gravar_leituras(banco, leituras_por_hora(15.0))

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["fruta"] == "manga"
    assert alerta["nivel"] == "LARANJA"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (manga) acumulou 20 °C·h acima de 13 °C: "
        "inspecionar antes do embarque."
    )


def test_risco_termico_tem_a_data_da_ultima_leitura_em_utc(cliente, banco):
    criar_lote(cliente)
    # ultima leitura: 10 h depois das 09:00 = 19:00 UTC
    gravar_leituras(banco, leituras_por_hora(5.0))

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["data_hora"] == "2026-10-24T19:00:00Z"


def test_menos_de_5_graus_hora_nao_gera_alerta_de_risco(cliente, banco):
    criar_lote(cliente)
    # 1 °C acima do limite por 4 h = 4 °C·h -> VERDE
    gravar_leituras(banco, leituras_por_hora(3.0, horas=4))
    assert alertas_do_tipo(cliente, "risco_termico") == []


# ---------- alertas: porta aberta ----------

def test_porta_aberta_com_mensagem_no_horario_de_recife(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=5.0),
        nova_leitura(em(12, 0, 20), 1.0, lux=640.0),    # 21:00:20 UTC, porta abre
        nova_leitura(em(12, 20, 20), 1.0, lux=880.0),
        nova_leitura(em(12, 40, 20), 1.0, lux=700.0),   # 40 min depois
        nova_leitura(em(13, 0, 20), 1.0, lux=5.0),      # fecha
    ])

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 1
    assert alertas[0]["lote_id"] == lote["id"]
    assert alertas[0]["fruta"] == "uva"
    assert alertas[0]["tipo"] == "porta_aberta"
    assert alertas[0]["nivel"] == "AMARELO"
    # 21:00:20Z vira 18:00 em Recife (UTC-3)
    assert alertas[0]["mensagem"] == (
        f"Lote {lote['id']} (uva): porta aberta por 40 min às 18:00 de 24/10."
    )
    # o campo data_hora continua em UTC
    assert alertas[0]["data_hora"] == "2026-10-24T21:00:20Z"


def test_porta_aberta_depois_da_meia_noite_utc_usa_a_data_de_recife(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=5.0),
        # 02:30 UTC de 25/10 = 23:30 de 24/10 em Recife
        nova_leitura(em(17, 30), 1.0, lux=640.0),
        nova_leitura(em(17, 50), 1.0, lux=640.0),
        nova_leitura(em(18, 10), 1.0, lux=5.0),
    ])

    alerta = alertas_do_tipo(cliente, "porta_aberta")[0]
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva): porta aberta por 20 min às 23:30 de 24/10."
    )
    assert alerta["data_hora"] == "2026-10-25T02:30:00Z"


def test_cada_abertura_de_porta_gera_um_alerta(cliente, banco):
    criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=640.0),
        nova_leitura(em(0, 10), 1.0, lux=640.0),
        nova_leitura(em(1), 1.0, lux=5.0),
        nova_leitura(em(2), 1.0, lux=640.0),
        nova_leitura(em(2, 10), 1.0, lux=640.0),
        nova_leitura(em(3), 1.0, lux=5.0),
    ])

    assert len(alertas_do_tipo(cliente, "porta_aberta")) == 2


def test_lote_com_porta_aberta_e_temperatura_boa_so_tem_alerta_de_porta(cliente, banco):
    criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=640.0),
        nova_leitura(em(0, 30), 1.0, lux=640.0),
        nova_leitura(em(1), 1.0, lux=5.0),
    ])

    tipos = []
    for alerta in cliente.get("/api/alertas").json():
        tipos.append(alerta["tipo"])
    assert tipos == ["porta_aberta"]


# ---------- alertas: ordem e formato ----------

def test_alertas_do_mais_grave_para_o_mais_leve(cliente, banco):
    criar_lote(cliente)
    # temperatura em 7 °C = 50 °C·h (VERMELHO), com uma abertura de porta (AMARELO)
    gravar_leituras(banco, leituras_por_hora(7.0, horas_com_porta_aberta=[3, 4]))

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 2
    assert (alertas[0]["tipo"], alertas[0]["nivel"]) == ("risco_termico", "VERMELHO")
    assert (alertas[1]["tipo"], alertas[1]["nivel"]) == ("porta_aberta", "AMARELO")


def test_alerta_laranja_vem_antes_do_alerta_de_porta(cliente, banco):
    criar_lote(cliente)
    # 5 °C = 30 °C·h (LARANJA), com uma abertura de porta (AMARELO)
    gravar_leituras(banco, leituras_por_hora(5.0, horas_com_porta_aberta=[3, 4]))

    niveis = []
    for alerta in cliente.get("/api/alertas").json():
        niveis.append(alerta["nivel"])
    assert niveis == ["LARANJA", "AMARELO"]


def test_alerta_tem_todos_os_campos_do_contrato(cliente, banco):
    criar_lote(cliente)
    gravar_leituras(banco, leituras_por_hora(5.0))

    alerta = cliente.get("/api/alertas").json()[0]
    assert set(alerta.keys()) == {"lote_id", "fruta", "tipo", "nivel", "mensagem", "data_hora"}


def test_datas_dos_alertas_terminam_em_z(cliente, banco):
    criar_lote(cliente)
    gravar_leituras(banco, leituras_por_hora(5.0, horas_com_porta_aberta=[3, 4]))

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 2
    for alerta in alertas:
        conferir_data_utc(alerta["data_hora"])


# ---------- sincronizar ----------

def test_sincronizar_conta_recebidas_novas_e_descartadas(cliente, monkeypatch):
    criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_do_thingspeak(1, em_utc(1), 1.0),
        leitura_do_thingspeak(2, em_utc(1, 0, 20), 1.2),
        leitura_do_thingspeak(3, em_utc(1, 0, 40), 1.4),
        leitura_do_thingspeak(4, em_utc(1, 1, 0), 999.0),    # impossivel
        leitura_do_thingspeak(5, em_utc(1, 1, 20), None),    # sem temperatura
    ])

    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200
    assert resposta.json() == {"canal": 3493443, "recebidas": 5, "novas": 3, "descartadas": 2}


def test_sincronizar_grava_as_leituras_novas_no_lote(cliente, monkeypatch):
    lote = criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_do_thingspeak(1, em_utc(1), 1.0, umidade=88.0, lux=5.0),
        leitura_do_thingspeak(2, em_utc(1, 0, 20), 6.0, umidade=90.0, lux=640.0),
        leitura_do_thingspeak(3, em_utc(1, 0, 40), 999.0),
    ])

    cliente.post("/api/sincronizar")

    leituras = leituras_do_lote(cliente, lote)
    datas = []
    for leitura in leituras:
        datas.append(leitura["data_hora"])
    assert datas == ["2026-10-24T10:00:00Z", "2026-10-24T10:00:20Z"]
    assert leituras[0]["temperatura_c"] == 1.0
    assert leituras[0]["umidade_pct"] == 88.0
    assert leituras[1]["fora_faixa_temp"] is True
    assert leituras[1]["porta_aberta"] is True


def test_sincronizar_duas_vezes_nao_duplica_leituras(cliente, monkeypatch):
    lote = criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_do_thingspeak(1, em_utc(1), 1.0),
        leitura_do_thingspeak(2, em_utc(1, 0, 20), 1.2),
        leitura_do_thingspeak(3, em_utc(1, 0, 40), 999.0),
    ])

    primeira = cliente.post("/api/sincronizar").json()
    segunda = cliente.post("/api/sincronizar").json()

    assert primeira["novas"] == 2
    assert segunda["recebidas"] == 3
    assert segunda["novas"] == 0
    assert segunda["descartadas"] == 1
    assert len(leituras_do_lote(cliente, lote)) == 2


def test_sincronizar_de_novo_grava_so_as_que_ainda_nao_existem(cliente, monkeypatch):
    lote = criar_lote(cliente)
    antigas = [
        leitura_do_thingspeak(1, em_utc(1), 1.0),
        leitura_do_thingspeak(2, em_utc(1, 0, 20), 1.2),
    ]
    thingspeak_devolve(monkeypatch, antigas)
    cliente.post("/api/sincronizar")

    nova = leitura_do_thingspeak(3, em_utc(1, 0, 40), 1.4)
    thingspeak_devolve(monkeypatch, antigas + [nova])
    resposta = cliente.post("/api/sincronizar").json()

    assert resposta["recebidas"] == 3
    assert resposta["novas"] == 1
    assert len(leituras_do_lote(cliente, lote)) == 3


def test_sincronizar_sem_leituras_no_thingspeak(cliente, monkeypatch):
    thingspeak_devolve(monkeypatch, [])

    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200
    assert resposta.json() == {"canal": 3493443, "recebidas": 0, "novas": 0, "descartadas": 0}


def test_sincronizar_com_thingspeak_fora_do_ar_devolve_502(cliente, monkeypatch):
    thingspeak_fora_do_ar(monkeypatch)

    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 502
    corpo = resposta.json()
    assert list(corpo.keys()) == ["erro"]
    assert corpo["erro"] != ""


def test_sincronizar_com_thingspeak_fora_do_ar_nao_grava_nada(cliente, monkeypatch):
    lote = criar_lote(cliente)
    thingspeak_fora_do_ar(monkeypatch)
    cliente.post("/api/sincronizar")

    assert leituras_do_lote(cliente, lote) == []


def test_leituras_sincronizadas_entram_na_analise_e_nos_alertas(cliente, monkeypatch):
    lote = criar_lote(cliente)
    # 11 leituras, uma por hora, a 5 °C: 3 °C acima do limite por 10 h = 30 °C·h
    leituras = []
    for hora in range(0, 11):
        leituras.append(leitura_do_thingspeak(hora + 1, em_utc(hora), 5.0))
    thingspeak_devolve(monkeypatch, leituras)
    resposta = cliente.post("/api/sincronizar").json()
    assert resposta["novas"] == 11

    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora"] == 30.0
    assert analise["nivel"] == "LARANJA"
    assert alertas_do_tipo(cliente, "risco_termico")[0]["nivel"] == "LARANJA"
