"""
Testes de caixa-preta de GET /api/alertas e POST /api/sincronizar, escritos a
partir de docs/api-contrato.md.

A sincronizacao nunca acessa a internet: a busca no ThingSpeak e trocada
por uma funcao falsa (monkeypatch).
"""

from datetime import datetime, timedelta, timezone

from app import app
from models.banco import abrir_sessao
from models.tabelas import Leitura
from services import thingspeak
from services.thingspeak import ErroThingSpeak

INICIO = datetime(2026, 10, 24, 9, 0, 0)  # 24/10/2026 09:00 UTC

LOTE_UVA = {
    "fruta": "uva",
    "origem": "Packing house Petrolina",
    "porto_destino": "Suape",
    "inicio": "2026-10-24T09:00:00Z",
}


# ---------- funcoes auxiliares ----------

def criar_lote(cliente, **mudancas):
    corpo = {**LOTE_UVA, **mudancas}
    resposta = cliente.post("/api/lotes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def em(horas, minutos=0, segundos=0):
    """Horario a 'horas' do inicio do lote (09:00 UTC de 24/10)."""
    return INICIO + timedelta(hours=horas, minutes=minutos, seconds=segundos)


def gravar_leituras(leituras):
    """
    Grava leituras direto no banco de teste (a mesma sessao que a API usa).
    Cada item e (data_hora em UTC, temperatura, umidade, luminosidade).
    """
    sessao = next(app.dependency_overrides[abrir_sessao]())
    for numero, (data_hora, temperatura, umidade, lux) in enumerate(leituras, start=1):
        sessao.add(Leitura(
            entry_id=numero,
            data_hora=data_hora,
            temperatura_c=temperatura,
            umidade_pct=umidade,
            luminosidade_lux=lux,
        ))
    sessao.commit()
    sessao.close()


def gravar_temperatura_constante(temperatura, horas=10):
    """Uma leitura por hora, da hora 0 ate 'horas', sempre com a mesma temperatura."""
    gravar_leituras([(em(h), temperatura, 90.0, None) for h in range(0, horas + 1)])


def leitura_ts(entry_id, data_hora, temperatura, umidade=90.0, lux=None):
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
    def buscar_falso(*args, **kwargs):
        return list(leituras)

    monkeypatch.setattr(thingspeak, "buscar_leituras", buscar_falso)


def thingspeak_fora_do_ar(monkeypatch):
    def buscar_falso(*args, **kwargs):
        raise ErroThingSpeak("Falha ao consultar o ThingSpeak: fora do ar")

    monkeypatch.setattr(thingspeak, "buscar_leituras", buscar_falso)


def alertas_do_tipo(cliente, tipo):
    alertas = cliente.get("/api/alertas").json()
    return [a for a in alertas if a["tipo"] == tipo]


# ---------- alertas: quando existem ----------

def test_sem_lotes_nao_ha_alertas(cliente):
    resposta = cliente.get("/api/alertas")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_lote_sem_leituras_nao_gera_alerta(cliente):
    criar_lote(cliente)
    assert cliente.get("/api/alertas").json() == []


def test_lote_verde_sem_porta_aberta_nao_gera_alerta(cliente):
    criar_lote(cliente)
    gravar_temperatura_constante(1.0)
    assert cliente.get("/api/alertas").json() == []


def test_lote_encerrado_nao_gera_alerta(cliente):
    lote = criar_lote(cliente)
    # 3 °C acima do limite por 10 h e porta aberta: geraria dois alertas se estivesse em transito
    gravar_leituras([(em(h), 5.0, 90.0, 640.0 if h in (3, 4) else None) for h in range(0, 11)])
    assert len(cliente.get("/api/alertas").json()) == 2

    cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-24T20:00:00Z"})
    assert cliente.get("/api/alertas").json() == []


# ---------- alertas: risco termico ----------

def test_risco_termico_amarelo_com_mensagem_do_contrato(cliente):
    lote = criar_lote(cliente)
    # 1 °C acima do limite (2 °C) por 6 h = 6 °C·h -> AMARELO (5 a menos de 20)
    gravar_temperatura_constante(3.0, horas=6)

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 1
    assert alertas[0]["lote_id"] == lote["id"]
    assert alertas[0]["fruta"] == "uva"
    assert alertas[0]["tipo"] == "risco_termico"
    assert alertas[0]["nivel"] == "AMARELO"
    assert alertas[0]["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 6 °C·h acima de 2 °C: priorizar na expedição."
    )


def test_risco_termico_laranja_com_mensagem_do_contrato(cliente):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h -> LARANJA
    gravar_temperatura_constante(5.0)

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["nivel"] == "LARANJA"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 30 °C·h acima de 2 °C: inspecionar antes do embarque."
    )


def test_risco_termico_vermelho_com_mensagem_do_contrato(cliente):
    lote = criar_lote(cliente)
    # 5 °C acima do limite (2 °C) por 10 h = 50 °C·h -> VERMELHO
    gravar_temperatura_constante(7.0)

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["nivel"] == "VERMELHO"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 50 °C·h acima de 2 °C: "
        "redirecionar para mercado interno ou processamento."
    )


def test_risco_termico_usa_o_limite_da_fruta_do_lote(cliente):
    lote = criar_lote(cliente, fruta="manga")
    # limite da manga = 13 °C; 2 °C acima por 10 h = 20 °C·h -> LARANJA (20 ja e laranja)
    gravar_temperatura_constante(15.0)

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["fruta"] == "manga"
    assert alerta["nivel"] == "LARANJA"
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (manga) acumulou 20 °C·h acima de 13 °C: inspecionar antes do embarque."
    )


def test_risco_termico_tem_a_data_da_ultima_leitura_em_utc(cliente):
    criar_lote(cliente)
    gravar_temperatura_constante(5.0)  # ultima leitura: 10 h depois das 09:00 = 19:00 UTC

    alerta = alertas_do_tipo(cliente, "risco_termico")[0]
    assert alerta["data_hora"] == "2026-10-24T19:00:00Z"


def test_menos_de_5_graus_hora_nao_gera_alerta_de_risco(cliente):
    criar_lote(cliente)
    # 1 °C acima do limite por 4 h = 4 °C·h -> VERDE
    gravar_temperatura_constante(3.0, horas=4)
    assert alertas_do_tipo(cliente, "risco_termico") == []


# ---------- alertas: porta aberta ----------

def test_porta_aberta_com_mensagem_no_horario_de_recife(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (em(0), 1.0, 90.0, 5.0),
        (datetime(2026, 10, 24, 21, 0, 20), 1.0, 90.0, 640.0),   # porta abre
        (datetime(2026, 10, 24, 21, 20, 20), 1.0, 90.0, 880.0),
        (datetime(2026, 10, 24, 21, 40, 20), 1.0, 90.0, 700.0),  # 40 min depois
        (datetime(2026, 10, 24, 22, 0, 20), 1.0, 90.0, 5.0),     # fecha
    ])

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 1
    assert alertas[0]["lote_id"] == lote["id"]
    assert alertas[0]["fruta"] == "uva"
    assert alertas[0]["tipo"] == "porta_aberta"
    assert alertas[0]["nivel"] == "AMARELO"
    # 21:00:20Z vira 18:00 em Recife (UTC-3)
    assert alertas[0]["mensagem"] == f"Lote {lote['id']} (uva): porta aberta por 40 min às 18:00 de 24/10."
    # o campo data_hora continua em UTC
    assert alertas[0]["data_hora"] == "2026-10-24T21:00:20Z"


def test_porta_aberta_depois_da_meia_noite_utc_usa_a_data_de_recife(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (em(0), 1.0, 90.0, 5.0),
        (datetime(2026, 10, 25, 2, 30, 0), 1.0, 90.0, 640.0),  # 23:30 do dia 24 em Recife
        (datetime(2026, 10, 25, 2, 50, 0), 1.0, 90.0, 640.0),
        (datetime(2026, 10, 25, 3, 10, 0), 1.0, 90.0, 5.0),
    ])

    alerta = alertas_do_tipo(cliente, "porta_aberta")[0]
    assert alerta["mensagem"] == f"Lote {lote['id']} (uva): porta aberta por 20 min às 23:30 de 24/10."
    assert alerta["data_hora"] == "2026-10-25T02:30:00Z"


def test_cada_abertura_de_porta_gera_um_alerta(cliente):
    criar_lote(cliente)
    gravar_leituras([
        (em(0), 1.0, 90.0, 640.0),
        (em(0, 10), 1.0, 90.0, 640.0),
        (em(1), 1.0, 90.0, 5.0),
        (em(2), 1.0, 90.0, 640.0),
        (em(2, 10), 1.0, 90.0, 640.0),
        (em(3), 1.0, 90.0, 5.0),
    ])

    assert len(alertas_do_tipo(cliente, "porta_aberta")) == 2


def test_lote_com_porta_aberta_e_temperatura_boa_so_tem_alerta_de_porta(cliente):
    criar_lote(cliente)
    gravar_leituras([
        (em(0), 1.0, 90.0, 640.0),
        (em(0, 30), 1.0, 90.0, 640.0),
        (em(1), 1.0, 90.0, 5.0),
    ])

    tipos = [a["tipo"] for a in cliente.get("/api/alertas").json()]
    assert tipos == ["porta_aberta"]


# ---------- alertas: ordem e formato ----------

def test_alertas_do_mais_grave_para_o_mais_leve(cliente):
    criar_lote(cliente)
    # temperatura em 7 °C = 50 °C·h (VERMELHO), com uma abertura de porta (AMARELO)
    gravar_leituras([(em(h), 7.0, 90.0, 640.0 if h in (3, 4) else None) for h in range(0, 11)])

    alertas = cliente.get("/api/alertas").json()
    assert [(a["tipo"], a["nivel"]) for a in alertas] == [
        ("risco_termico", "VERMELHO"),
        ("porta_aberta", "AMARELO"),
    ]


def test_alerta_laranja_vem_antes_do_alerta_de_porta(cliente):
    criar_lote(cliente)
    # 5 °C = 30 °C·h (LARANJA), com uma abertura de porta (AMARELO)
    gravar_leituras([(em(h), 5.0, 90.0, 640.0 if h in (3, 4) else None) for h in range(0, 11)])

    alertas = cliente.get("/api/alertas").json()
    assert [a["nivel"] for a in alertas] == ["LARANJA", "AMARELO"]


def test_alerta_tem_todos_os_campos_do_contrato(cliente):
    criar_lote(cliente)
    gravar_temperatura_constante(5.0)

    alerta = cliente.get("/api/alertas").json()[0]
    assert set(alerta.keys()) == {"lote_id", "fruta", "tipo", "nivel", "mensagem", "data_hora"}


def test_datas_dos_alertas_terminam_em_z(cliente):
    criar_lote(cliente)
    gravar_leituras([(em(h), 5.0, 90.0, 640.0 if h in (3, 4) else None) for h in range(0, 11)])

    alertas = cliente.get("/api/alertas").json()
    assert len(alertas) == 2
    for alerta in alertas:
        assert alerta["data_hora"].endswith("Z")
        datetime.strptime(alerta["data_hora"], "%Y-%m-%dT%H:%M:%SZ")


# ---------- sincronizar ----------

def test_sincronizar_conta_recebidas_novas_e_descartadas(cliente, monkeypatch):
    criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_ts(1, datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc), 1.0),
        leitura_ts(2, datetime(2026, 10, 24, 10, 0, 20, tzinfo=timezone.utc), 1.2),
        leitura_ts(3, datetime(2026, 10, 24, 10, 0, 40, tzinfo=timezone.utc), 1.4),
        leitura_ts(4, datetime(2026, 10, 24, 10, 1, 0, tzinfo=timezone.utc), 999.0),  # impossivel
        leitura_ts(5, datetime(2026, 10, 24, 10, 1, 20, tzinfo=timezone.utc), None),  # sem temperatura
    ])

    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200
    assert resposta.json() == {"canal": 3493443, "recebidas": 5, "novas": 3, "descartadas": 2}


def test_sincronizar_grava_as_leituras_novas_no_lote(cliente, monkeypatch):
    lote = criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_ts(1, datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc), 1.0, 88.0, 5.0),
        leitura_ts(2, datetime(2026, 10, 24, 10, 0, 20, tzinfo=timezone.utc), 6.0, 90.0, 640.0),
        leitura_ts(3, datetime(2026, 10, 24, 10, 0, 40, tzinfo=timezone.utc), 999.0),
    ])

    cliente.post("/api/sincronizar")

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert [l["data_hora"] for l in leituras] == ["2026-10-24T10:00:00Z", "2026-10-24T10:00:20Z"]
    assert leituras[0]["temperatura_c"] == 1.0
    assert leituras[0]["umidade_pct"] == 88.0
    assert leituras[1]["fora_faixa_temp"] is True
    assert leituras[1]["porta_aberta"] is True


def test_sincronizar_duas_vezes_nao_duplica_leituras(cliente, monkeypatch):
    lote = criar_lote(cliente)
    thingspeak_devolve(monkeypatch, [
        leitura_ts(1, datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc), 1.0),
        leitura_ts(2, datetime(2026, 10, 24, 10, 0, 20, tzinfo=timezone.utc), 1.2),
        leitura_ts(3, datetime(2026, 10, 24, 10, 0, 40, tzinfo=timezone.utc), 999.0),
    ])

    primeira = cliente.post("/api/sincronizar").json()
    segunda = cliente.post("/api/sincronizar").json()

    assert primeira["novas"] == 2
    assert segunda["recebidas"] == 3
    assert segunda["novas"] == 0
    assert segunda["descartadas"] == 1
    assert len(cliente.get(f"/api/lotes/{lote['id']}/leituras").json()) == 2


def test_sincronizar_de_novo_grava_so_as_que_ainda_nao_existem(cliente, monkeypatch):
    lote = criar_lote(cliente)
    antigas = [
        leitura_ts(1, datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc), 1.0),
        leitura_ts(2, datetime(2026, 10, 24, 10, 0, 20, tzinfo=timezone.utc), 1.2),
    ]
    thingspeak_devolve(monkeypatch, antigas)
    cliente.post("/api/sincronizar")

    nova = leitura_ts(3, datetime(2026, 10, 24, 10, 0, 40, tzinfo=timezone.utc), 1.4)
    thingspeak_devolve(monkeypatch, antigas + [nova])
    resposta = cliente.post("/api/sincronizar").json()

    assert resposta["recebidas"] == 3
    assert resposta["novas"] == 1
    assert len(cliente.get(f"/api/lotes/{lote['id']}/leituras").json()) == 3


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

    assert cliente.get(f"/api/lotes/{lote['id']}/leituras").json() == []


def test_leituras_sincronizadas_entram_na_analise_e_nos_alertas(cliente, monkeypatch):
    lote = criar_lote(cliente)
    # 11 leituras, uma por hora, a 5 °C: 3 °C acima do limite por 10 h = 30 °C·h
    thingspeak_devolve(monkeypatch, [
        leitura_ts(h + 1, datetime(2026, 10, 24, 9, 0, 0, tzinfo=timezone.utc) + timedelta(hours=h), 5.0)
        for h in range(0, 11)
    ])
    resposta = cliente.post("/api/sincronizar").json()
    assert resposta["novas"] == 11

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["graus_hora"] == 30.0
    assert analise["nivel"] == "LARANJA"
    assert alertas_do_tipo(cliente, "risco_termico")[0]["nivel"] == "LARANJA"
