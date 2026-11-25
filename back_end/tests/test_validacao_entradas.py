"""Testes das regras de validacao dos JSON recebidos (models/entradas.py)."""

import pytest
from pydantic import ValidationError

from models.entradas import (
    DadosDeLogin,
    DispositivoNovo,
    Encerramento,
    FaixaSegura,
    FrutaNova,
    LoteNovo,
)
from models.limites import TEMP_FISICA_MAX, TEMP_FISICA_MIN

FAIXA = {"temp_min_c": 0, "temp_max_c": 8, "umidade_min_pct": 85, "umidade_max_pct": 95}
LOTE = {"fruta": "uva", "produtor": "Fazenda A", "origem": "Petrolina", "destino": "Rotterdam", "tipo_destino": "porto"}


def test_limites_fisicos_do_sensor():
    assert TEMP_FISICA_MIN == -40.0
    assert TEMP_FISICA_MAX == 80.0


def test_faixa_valida_e_aceita():
    assert FaixaSegura(**FAIXA).temp_max_c == 8


@pytest.mark.parametrize("campo, valor", [
    ("temp_min_c", TEMP_FISICA_MIN - 0.1),
    ("temp_max_c", TEMP_FISICA_MAX + 0.1),
    ("umidade_min_pct", -1),
    ("umidade_max_pct", 100.1),
    ("temp_min_c", float("nan")),
    ("temp_max_c", float("inf")),
])
def test_faixa_recusa_valores_fora_do_limite(campo, valor):
    with pytest.raises(ValidationError):
        FaixaSegura(**{**FAIXA, campo: valor})


@pytest.mark.parametrize("campo, valor", [
    ("temp_min_c", TEMP_FISICA_MIN), ("temp_max_c", TEMP_FISICA_MAX),
    ("umidade_min_pct", 0), ("umidade_max_pct", 100),
])
def test_faixa_aceita_os_valores_exatos_dos_limites(campo, valor):
    assert FaixaSegura(**{**FAIXA, campo: valor})


def test_faixa_exige_todos_os_campos():
    with pytest.raises(ValidationError):
        FaixaSegura(temp_min_c=0, temp_max_c=8)


@pytest.mark.parametrize("id_fruta", ["uva", "manga-palmer", "goiaba_2"])
def test_fruta_aceita_ids_no_formato_certo(id_fruta):
    assert FrutaNova(id=id_fruta, nome="Fruta", fonte="Estudo", **FAIXA).id == id_fruta


@pytest.mark.parametrize("id_fruta", ["Uva", "uva madura", "maçã", "uva/1", ""])
def test_fruta_recusa_ids_fora_do_formato(id_fruta):
    with pytest.raises(ValidationError):
        FrutaNova(id=id_fruta, nome="Fruta", fonte="Estudo", **FAIXA)


@pytest.mark.parametrize("campo", ["nome", "fonte"])
def test_fruta_recusa_texto_vazio(campo):
    dados = {"id": "uva", "nome": "Uva", "fonte": "Estudo", **FAIXA, campo: ""}
    with pytest.raises(ValidationError):
        FrutaNova(**dados)


def test_lote_minimo_e_aceito_com_opcionais_vazios():
    lote = LoteNovo(**LOTE)
    assert lote.inicio is None and lote.faixa_segura is None and lote.dispositivo_id is None


def test_lote_aceita_faixa_e_dispositivo():
    lote = LoteNovo(**LOTE, faixa_segura=FAIXA, dispositivo_id=3, inicio="2026-10-24T09:00:00Z")
    assert lote.faixa_segura.temp_min_c == 0
    assert lote.dispositivo_id == 3
    assert lote.inicio.year == 2026


@pytest.mark.parametrize("campo", ["produtor", "origem", "destino"])
def test_lote_recusa_texto_vazio(campo):
    with pytest.raises(ValidationError):
        LoteNovo(**{**LOTE, campo: ""})


@pytest.mark.parametrize("dispositivo", [0, -1])
def test_lote_recusa_dispositivo_nao_positivo(dispositivo):
    with pytest.raises(ValidationError):
        LoteNovo(**LOTE, dispositivo_id=dispositivo)


def test_lote_recusa_data_de_inicio_invalida():
    with pytest.raises(ValidationError):
        LoteNovo(**LOTE, inicio="ontem")


def test_dispositivo_aceita_canal_valido():
    assert DispositivoNovo(nome="ESP32", canal=123).canal == 123
    assert DispositivoNovo(nome="x" * 80, canal=2147483647)


@pytest.mark.parametrize("dados", [
    {"nome": "", "canal": 1},
    {"nome": "x" * 81, "canal": 1},
    {"nome": "ESP32", "canal": 0},
    {"nome": "ESP32", "canal": -5},
    {"nome": "ESP32", "canal": 2147483648},
    {"nome": "ESP32", "canal": "abc"},
])
def test_dispositivo_recusa_dados_invalidos(dados):
    with pytest.raises(ValidationError):
        DispositivoNovo(**dados)


def test_login_valido_e_limites_de_tamanho():
    assert DadosDeLogin(usuario="ana", senha="x" * 200)
    with pytest.raises(ValidationError):
        DadosDeLogin(usuario="ana", senha="x" * 201)
    with pytest.raises(ValidationError):
        DadosDeLogin(usuario="x" * 101, senha="abc")


@pytest.mark.parametrize("dados", [{"usuario": "", "senha": "abc"}, {"usuario": "ana", "senha": ""}, {"usuario": "ana"}])
def test_login_recusa_campos_vazios_ou_ausentes(dados):
    with pytest.raises(ValidationError):
        DadosDeLogin(**dados)


def test_encerramento_aceita_sem_data():
    assert Encerramento().fim is None
    assert Encerramento(fim="2026-10-25T17:30:00Z").fim.day == 25
