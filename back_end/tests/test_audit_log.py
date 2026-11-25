"""Testes de security/audit_log.py: leitura de configuracao e registro de bloqueios."""

import logging

from security import audit_log


def test_codigo_da_missao_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("PLANTSYNC_CODIGO_MISSAO", "ABC123")
    assert audit_log.get_mission_code() == "ABC123"


def test_codigo_da_missao_tem_valor_padrao(monkeypatch):
    monkeypatch.delenv("PLANTSYNC_CODIGO_MISSAO", raising=False)
    assert audit_log.get_mission_code() == "XXXXXX"


def test_janela_do_totp_padrao_e_configuravel(monkeypatch):
    monkeypatch.delenv("PLANTSYNC_TOTP_WINDOW", raising=False)
    assert audit_log.get_totp_window() == 1
    monkeypatch.setenv("PLANTSYNC_TOTP_WINDOW", "2")
    assert audit_log.get_totp_window() == 2


def test_chave_do_totp_vazia_por_padrao(monkeypatch):
    monkeypatch.delenv("PLANTSYNC_TOTP_KEY", raising=False)
    assert audit_log.get_totp_key() == ""
    monkeypatch.setenv("PLANTSYNC_TOTP_KEY", "chave")
    assert audit_log.get_totp_key() == "chave"


def test_bloqueio_e_registrado_com_controle_motivo_e_ids(monkeypatch, caplog, capsys):
    monkeypatch.setenv("PLANTSYNC_CODIGO_MISSAO", "ZZ9999")
    with caplog.at_level(logging.WARNING, logger="plantsync.security"):
        audit_log.log_security_block("IDOR", "recurso_de_outra_empresa", user_id=7, resource_id=42)
    esperado = "[MISSAO:ZZ9999][BLOQUEIO][IDOR] motivo=recurso_de_outra_empresa | user_id=7 | resource_id=42"
    assert esperado in caplog.text or esperado in caplog.messages
    assert esperado in capsys.readouterr().err


def test_bloqueio_sem_ids_registra_none(caplog, capsys):
    audit_log.log_security_block("2FA", "codigo_invalido")
    assert "user_id=None | resource_id=None" in capsys.readouterr().err
