"""Testes das conversoes de data e hora de services/datas.py."""

from datetime import datetime, timedelta, timezone

from services.datas import (
    agora_utc,
    formatar_para_thingspeak,
    formatar_utc,
    hora_recife,
    para_utc,
)


def test_agora_utc_devolve_data_sem_fuso():
    assert agora_utc().tzinfo is None


def test_para_utc_mantem_data_sem_fuso():
    data = datetime(2026, 10, 24, 12, 0, 0)
    assert para_utc(data) == data


def test_para_utc_converte_data_com_fuso():
    recife = timezone(timedelta(hours=-3))
    data = datetime(2026, 10, 24, 9, 0, 0, tzinfo=recife)
    assert para_utc(data) == datetime(2026, 10, 24, 12, 0, 0)
    assert para_utc(data).tzinfo is None


def test_formatar_utc_segue_o_contrato():
    assert formatar_utc(datetime(2026, 10, 25, 17, 30, 0)) == "2026-10-25T17:30:00Z"


def test_formatar_utc_mantem_none():
    assert formatar_utc(None) is None


def test_formatar_para_thingspeak_usa_utc():
    recife = timezone(timedelta(hours=-3))
    data = datetime(2026, 10, 24, 9, 0, 0, tzinfo=recife)
    assert formatar_para_thingspeak(data) == "2026-10-24 12:00:00"


def test_hora_recife_converte_de_utc():
    # Recife fica em UTC-3.
    assert hora_recife(datetime(2026, 10, 24, 21, 0, 0)) == "18:00 de 24/10"


def test_hora_recife_vira_o_dia_anterior():
    assert hora_recife(datetime(2026, 10, 25, 1, 30, 0)) == "22:30 de 24/10"
