from datetime import datetime, timezone

from services.thingspeak import converter_feed, converter_numero


def test_converte_entrada_do_canal():
    # Formato real devolvido pelo canal 3493443 em 29/09/2026
    feed = {
        "created_at": "2026-09-29T22:32:34Z",
        "entry_id": 16,
        "field1": "25.10",
        "field2": "75.00",
    }
    leitura = converter_feed(feed)
    assert leitura["entry_id"] == 16
    assert leitura["data_hora"] == datetime(2026, 9, 29, 22, 32, 34, tzinfo=timezone.utc)
    assert leitura["temperatura_c"] == 25.1
    assert leitura["umidade_pct"] == 75.0
    assert leitura["luminosidade_lux"] is None


def test_campo_vazio_ou_invalido_vira_none():
    assert converter_numero("") is None
    assert converter_numero(None) is None
    assert converter_numero("nan?") is None
    assert converter_numero("3.5") == 3.5
