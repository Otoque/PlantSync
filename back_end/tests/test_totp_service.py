"""Testes unitarios do 2FA (TOTP) em security/totp_service.py, sem passar pela API."""

import pyotp
import pytest
from cryptography.fernet import Fernet

from models.contas import Conta
from security import totp_service as totp


@pytest.fixture(autouse=True)
def chave_de_teste(monkeypatch):
    """Define uma chave de criptografia valida so para estes testes."""
    monkeypatch.setenv("PLANTSYNC_TOTP_KEY", Fernet.generate_key().decode())


@pytest.fixture
def sessao(banco):
    with banco() as sessao:
        yield sessao


@pytest.fixture
def conta(sessao):
    nova = Conta(nome="operador", email="operador@teste.com", sal="x", senha_hash="x")
    sessao.add(nova)
    sessao.commit()
    return nova


def configurar_2fa(sessao, conta):
    """Liga o 2FA da conta e devolve o gerador de codigos do aplicativo."""
    resultado = totp.setup_user_2fa(sessao, conta)
    segredo = totp.decrypt_secret(conta.totp_secret_encrypted)
    return pyotp.TOTP(segredo), resultado


def test_segredo_e_criptografado_e_volta_igual():
    cifrado = totp.encrypt_secret("JBSWY3DPEHPK3PXP")
    assert cifrado != "JBSWY3DPEHPK3PXP"
    assert totp.decrypt_secret(cifrado) == "JBSWY3DPEHPK3PXP"


def test_sem_chave_configurada_levanta_erro(monkeypatch):
    monkeypatch.setenv("PLANTSYNC_TOTP_KEY", "")
    with pytest.raises(RuntimeError):
        totp.encrypt_secret("qualquer")


def test_hash_do_codigo_de_recuperacao_ignora_caixa_hifen_e_espacos():
    assert totp._hash_recovery_code("ab12-cd34") == totp._hash_recovery_code(" AB12CD34 ")


def test_gera_oito_codigos_de_recuperacao_no_formato_certo(sessao, conta):
    codigos = totp.generate_recovery_codes(sessao, conta)
    assert len(codigos) == 8
    assert all(len(c) == 9 and c[4] == "-" for c in codigos)


def test_setup_devolve_uri_e_deixa_2fa_desativado_ate_confirmar(sessao, conta):
    _, resultado = configurar_2fa(sessao, conta)
    assert resultado["provisioning_uri"].startswith("otpauth://totp/")
    assert len(resultado["recovery_codes"]) == 8
    assert conta.totp_enabled is False


def test_verificar_sem_2fa_configurado(sessao, conta):
    assert totp.verify_user_totp(sessao, conta, "123456") == (False, "2fa_nao_configurado")


@pytest.mark.parametrize("codigo", ["", "12345", "1234567", "abcdef"])
def test_verificar_rejeita_formato_invalido(sessao, conta, codigo):
    configurar_2fa(sessao, conta)
    assert totp.verify_user_totp(sessao, conta, codigo) == (False, "formato_otp_invalido")


def test_verificar_aceita_codigo_correto(sessao, conta):
    gerador, _ = configurar_2fa(sessao, conta)
    assert totp.verify_user_totp(sessao, conta, gerador.now()) == (True, "ok")


def test_verificar_rejeita_codigo_errado(sessao, conta):
    gerador, _ = configurar_2fa(sessao, conta)
    errado = "000000" if gerador.now() != "000000" else "111111"
    ok, motivo = totp.verify_user_totp(sessao, conta, errado)
    assert (ok, motivo) == (False, "codigo_otp_invalido_ou_expirado")


def test_mesmo_codigo_nao_pode_ser_usado_duas_vezes(sessao, conta):
    gerador, _ = configurar_2fa(sessao, conta)
    codigo = gerador.now()
    assert totp.verify_user_totp(sessao, conta, codigo) == (True, "ok")
    assert totp.verify_user_totp(sessao, conta, codigo) == (False, "codigo_otp_ja_utilizado")


def test_check_only_nao_consome_o_codigo(sessao, conta):
    gerador, _ = configurar_2fa(sessao, conta)
    codigo = gerador.now()
    assert totp.verify_user_totp(sessao, conta, codigo, check_only=True) == (True, "ok")
    assert totp.verify_user_totp(sessao, conta, codigo) == (True, "ok")


def test_confirmar_2fa_ativa_a_conta(sessao, conta):
    gerador, _ = configurar_2fa(sessao, conta)
    assert totp.confirm_user_2fa(sessao, conta, gerador.now()) == (True, "ok")
    assert conta.totp_enabled is True


def test_codigo_de_recuperacao_so_vale_uma_vez(sessao, conta):
    codigos = totp.generate_recovery_codes(sessao, conta)
    assert totp.verify_and_consume_recovery_code(sessao, conta, codigos[0]) == (True, "ok")
    ok, motivo = totp.verify_and_consume_recovery_code(sessao, conta, codigos[0])
    assert (ok, motivo) == (False, "codigo_recuperacao_ja_utilizado")


def test_codigo_de_recuperacao_invalido_ou_ausente(sessao, conta):
    totp.generate_recovery_codes(sessao, conta)
    assert totp.verify_and_consume_recovery_code(sessao, conta, "") == (False, "codigo_recuperacao_ausente")
    assert totp.verify_and_consume_recovery_code(sessao, conta, "ZZZZ-ZZZZ") == (False, "codigo_recuperacao_invalido")


def test_gerar_novos_codigos_invalida_os_antigos(sessao, conta):
    antigos = totp.generate_recovery_codes(sessao, conta)
    totp.generate_recovery_codes(sessao, conta)
    ok, motivo = totp.verify_and_consume_recovery_code(sessao, conta, antigos[0])
    assert (ok, motivo) == (False, "codigo_recuperacao_invalido")


def test_token_mfa_e_consumido_uma_unica_vez(sessao, conta):
    token = totp.criar_mfa_token(sessao, conta)
    assert token.startswith(totp.PREFIXO_MFA)
    assert totp.consumir_mfa_token(sessao, token).id == conta.id
    assert totp.consumir_mfa_token(sessao, token) is None


@pytest.mark.parametrize("token", ["", None, "sem_prefixo", "psm_inexistente"])
def test_token_mfa_invalido_devolve_none(sessao, token):
    assert totp.consumir_mfa_token(sessao, token) is None
