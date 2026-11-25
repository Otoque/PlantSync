"""Testes das funcoes puras de senha e token em services/autenticacao.py."""

import re
from types import SimpleNamespace

import pytest

from services import autenticacao as aut

SAL = "00" * 16


def test_hash_da_senha_e_deterministico_para_o_mesmo_sal():
    assert aut.calcular_hash_da_senha("SenhaForte#2026", SAL) == aut.calcular_hash_da_senha("SenhaForte#2026", SAL)


def test_hash_da_senha_muda_com_a_senha_e_com_o_sal():
    base = aut.calcular_hash_da_senha("SenhaForte#2026", SAL)
    assert base != aut.calcular_hash_da_senha("SenhaForte#2027", SAL)
    assert base != aut.calcular_hash_da_senha("SenhaForte#2026", "11" * 16)


def test_hash_da_senha_tem_formato_hexadecimal_de_64_bytes():
    assert re.fullmatch(r"[0-9a-f]{128}", aut.calcular_hash_da_senha("abc", SAL))


def test_senha_nao_aparece_no_hash():
    assert "SenhaForte" not in aut.calcular_hash_da_senha("SenhaForte#2026", SAL)


def test_senha_confere_aceita_a_certa_e_recusa_a_errada():
    usuario = SimpleNamespace(sal=SAL, senha_hash=aut.calcular_hash_da_senha("SenhaForte#2026", SAL))
    assert aut.senha_confere("SenhaForte#2026", usuario) is True
    assert aut.senha_confere("senhaforte#2026", usuario) is False


def test_hash_do_token_e_sha256_estavel():
    assert aut.hash_do_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert aut.hash_do_token("abc") != aut.hash_do_token("abd")


def test_constantes_de_seguranca_nao_foram_enfraquecidas():
    assert aut.TAMANHO_MINIMO_DA_SENHA >= 12
    assert aut.VALIDADE_DO_TOKEN.total_seconds() <= 24 * 3600
    assert aut.SCRYPT_N >= 2**14
