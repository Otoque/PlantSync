from datetime import datetime, timedelta, timezone

from services import sincronizacao
from services.erros import ErroThingSpeak


AGORA = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
INICIO = AGORA - timedelta(hours=3)


def cadastrar_placa(cliente, canal, nome=None):
    resposta = cliente.post("/api/dispositivos", json={
        "nome": nome or f"Placa {canal}", "canal": canal,
    })
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def abrir_lote(cliente, placa=None, inicio=INICIO):
    return cliente.post("/api/lotes", json={
        "fruta": "uva", "produtor": "Bancada", "origem": "Petrolina",
        "destino": "Recife", "tipo_destino": "mercado_interno",
        "inicio": inicio.isoformat(), "dispositivo_id": placa,
    })


def leitura(entry_id, horas, temperatura):
    return {
        "entry_id": entry_id, "data_hora": INICIO + timedelta(hours=horas),
        "temperatura_c": temperatura, "umidade_pct": 89.0, "luminosidade_lux": None,
    }


def temperaturas(cliente, lote):
    resposta = cliente.get(f"/api/lotes/{lote}/leituras")
    assert resposta.status_code == 200
    return [item["temperatura_c"] for item in resposta.json()]


def test_cadastro_e_listagem_protegidos(cliente, cliente_sem_login):
    assert cliente_sem_login.get("/api/dispositivos").status_code == 401
    assert cliente_sem_login.post("/api/dispositivos", json={"canal": 41, "nome": "ESP"}).status_code == 401
    id_ = cadastrar_placa(cliente, 41, "ESP do caminhão")
    for canal in (41, sincronizacao.CANAL_THINGSPEAK):
        repetido = cliente.post("/api/dispositivos", json={"canal": canal, "nome": "Outro ESP"})
        assert repetido.status_code == 400
    assert cliente.get("/api/dispositivos").json()[1] == {
        "id": id_, "canal": 41, "nome": "ESP do caminhão", "ocupado": False,
    }


def test_separa_tres_viagens_com_mesmos_ids_e_horarios(cliente, monkeypatch):
    placa_a = cadastrar_placa(cliente, 41)
    placa_b = cadastrar_placa(cliente, 42)
    a, b, legado = (abrir_lote(cliente, placa) for placa in (placa_a, placa_b, None))
    assert [r.status_code for r in (a, b, legado)] == [201, 201, 201]
    a, b, legado = a.json(), b.json(), legado.json()
    assert a["dispositivo"]["canal"] == 41 and b["dispositivo"]["canal"] == 42
    assert "dispositivo" not in legado
    dados = {
        41: [leitura(1, 0, 15.0), leitura(2, 1, 15.0)],
        42: [leitura(1, 0, -9.0), leitura(2, 1, -9.0)],
        sincronizacao.CANAL_THINGSPEAK: [leitura(1, 0, 1.0), leitura(2, 1, 1.0)],
    }
    monkeypatch.setattr(sincronizacao, "agora_utc", lambda: AGORA.replace(tzinfo=None))
    monkeypatch.setattr(sincronizacao.thingspeak, "buscar_leituras", lambda canal, **_: dados[canal])
    sincronizada = cliente.post("/api/sincronizar")
    assert sincronizada.status_code == 200, sincronizada.text
    assert sincronizada.json()["novas"] == 6
    assert cliente.post("/api/sincronizar").json()["novas"] == 0
    assert temperaturas(cliente, a["id"]) == [15.0, 15.0]
    assert temperaturas(cliente, b["id"]) == [-9.0, -9.0]
    assert temperaturas(cliente, legado["id"]) == [1.0, 1.0]
    assert {item["lote_id"] for item in cliente.get("/api/alertas").json()} == {a["id"], b["id"]}
    assert "dispositivo" not in cliente.get(f"/api/publico/{a['codigo_publico']}").json()


def test_placa_ocupada_e_reuso_apenas_apos_fim(cliente):
    placa = cadastrar_placa(cliente, 41)
    assert abrir_lote(cliente, 999999).status_code == 400
    primeiro = abrir_lote(cliente, placa).json()
    assert abrir_lote(cliente, placa).status_code == 400
    assert cliente.get("/api/dispositivos").json()[1]["ocupado"]
    fim = INICIO + timedelta(hours=1)
    assert cliente.post(f"/api/lotes/{primeiro['id']}/encerrar", json={"fim": fim.isoformat()}).status_code == 200
    assert not cliente.get("/api/dispositivos").json()[1]["ocupado"]
    assert abrir_lote(cliente, placa, inicio=fim).status_code == 400
    assert abrir_lote(cliente, placa, inicio=fim + timedelta(seconds=1)).status_code == 201


def test_sincroniza_outra_placa_quando_um_canal_falha(cliente, monkeypatch):
    placa_a = cadastrar_placa(cliente, 41)
    placa_b = cadastrar_placa(cliente, 42)
    a = abrir_lote(cliente, placa_a).json()
    b = abrir_lote(cliente, placa_b).json()
    monkeypatch.setenv("THINGSPEAK_CHAVE_LEITURA_42", "chave-de-teste")

    def buscar(canal, desde, chave_leitura):
        if canal == 41:
            raise ErroThingSpeak("Canal fora do ar.")
        if canal == 42:
            assert chave_leitura == "chave-de-teste"
            assert desde == INICIO.replace(tzinfo=None)
            return [leitura(1, 1, 3.0)]
        return []

    monkeypatch.setattr(sincronizacao.thingspeak, "buscar_leituras", buscar)
    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["novas"] == 1
    assert [falha["canal"] for falha in resposta.json()["falhas"]] == [41]
    assert "chave-de-teste" not in resposta.text
    assert temperaturas(cliente, a["id"]) == []
    assert temperaturas(cliente, b["id"]) == [3.0]
