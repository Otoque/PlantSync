from datetime import datetime, timedelta

from services.analise import (
    analisar_lote,
    calcular_graus_hora,
    classificar_risco,
    detectar_eventos_porta,
    detectar_trechos_fora_da_faixa,
    limpar_leituras,
    nivel_mais_grave,
)

# Faixas e inicio proprios deste arquivo: estes testes chamam a analise direto,
# sem banco, por isso nao usam o tests/auxiliares.py.
FAIXA_UVA = {"temp_min_c": 0.0, "temp_max_c": 2.0, "umidade_min_pct": 85.0, "umidade_max_pct": 95.0}
FAIXA_MANGA = {
    "temp_min_c": 10.0,
    "temp_max_c": 13.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 90.0,
}
INICIO = datetime(2026, 10, 24, 9, 0, 0)


def leitura(horas, temperatura, luminosidade=None):
    """Cria uma leitura a 'horas' do inicio da viagem."""
    return {
        "data_hora": INICIO + timedelta(hours=horas),
        "temperatura_c": temperatura,
        "umidade_pct": 90.0,
        "luminosidade_lux": luminosidade,
    }


def test_graus_hora_zero_quando_tudo_dentro_da_faixa():
    leituras = [leitura(0, 1.0), leitura(1, 1.5), leitura(2, 2.0)]
    assert calcular_graus_hora(leituras, 0.0, 2.0) == (0.0, 0.0)


def test_graus_hora_soma_excesso_vezes_tempo():
    # 2 graus acima do limite durante 3 horas = 6 graus-hora
    leituras = [leitura(0, 4.0), leitura(1, 4.0), leitura(2, 4.0), leitura(3, 4.0)]
    assert calcular_graus_hora(leituras, 0.0, 2.0) == (6.0, 0.0)


def test_classificacao_nos_quatro_niveis():
    assert classificar_risco(0) == "VERDE"
    assert classificar_risco(4.9) == "VERDE"
    assert classificar_risco(5) == "AMARELO"
    assert classificar_risco(24) == "LARANJA"
    assert classificar_risco(50) == "VERMELHO"


def test_limpeza_tira_valor_impossivel_nulo_e_retransmissao():
    leituras = [
        leitura(1, 1.0),
        leitura(0, 1.0),
        leitura(1, 1.0),        # retransmissao com o mesmo horario
        leitura(2, 999.0),      # sensor com defeito
        leitura(3, None),       # sem temperatura
        leitura(4, 1.2),
    ]
    datas = []
    for limpa in limpar_leituras(leituras):
        datas.append(limpa["data_hora"])
    assert datas == [INICIO, INICIO + timedelta(hours=1), INICIO + timedelta(hours=4)]


def test_eventos_de_porta_agrupam_leituras_seguidas():
    leituras = [
        leitura(0, 1.0, 5),
        leitura(1, 1.0, 600),
        leitura(1.5, 1.0, 880),
        leitura(2, 1.0, 4),
        leitura(3, 1.0, 450),   # segunda abertura, ate o fim da viagem
    ]
    eventos = detectar_eventos_porta(leituras)
    assert len(eventos) == 2
    assert eventos[0]["duracao_min"] == 30.0
    assert eventos[0]["lux_max"] == 880
    assert eventos[1]["duracao_min"] == 0.0


def test_sem_luminosidade_nao_ha_porta_aberta():
    leituras = [leitura(0, 1.0), leitura(1, 1.0)]
    assert detectar_eventos_porta(leituras) == []


def test_analise_completa_de_um_lote():
    leituras = [leitura(0, 1.0), leitura(10, 5.0), leitura(20, 1.0)]
    analise = analisar_lote(leituras, FAIXA_UVA)
    # 3 graus acima do limite durante 10 horas = 30 graus-hora
    assert analise["graus_hora_acima"] == 30.0
    assert analise["nivel"] == "LARANJA"
    assert analise["amostras"] == 3
    assert analise["amostras_fora_faixa"] == 1
    assert analise["temp_max_c"] == 5.0
    assert "Inspeção física" in analise["recomendacao"]


def test_analise_de_lote_sem_leituras():
    analise = analisar_lote([], FAIXA_UVA)
    assert analise["nivel"] == "SEM_DADOS"
    assert analise["amostras"] == 0
    assert analise["temp_max_c"] is None


# ---------- risco nos dois lados da faixa (calor acima do teto e frio abaixo do piso) ----------

def test_manga_a_8_5_graus_por_72_horas_nao_pode_ser_verde():
    # O frio abaixo do piso precisa pesar no risco: uma manga a 8,5 graus
    # por 72 horas nao pode ficar VERDE (ela pode desenvolver corte negro).
    # 1,5 grau abaixo do piso (10) durante 72 horas = 108 graus-hora
    leituras = [leitura(0, 8.5), leitura(72, 8.5)]
    analise = analisar_lote(leituras, FAIXA_MANGA)
    assert analise["graus_hora_abaixo"] == 108.0
    assert analise["graus_hora_acima"] == 0.0
    assert analise["nivel_abaixo"] == "VERMELHO"
    assert analise["nivel"] != "VERDE"


def test_leitura_exatamente_no_piso_ou_no_teto_soma_zero():
    no_piso = [leitura(0, 10.0), leitura(5, 10.0)]
    no_teto = [leitura(0, 13.0), leitura(5, 13.0)]
    assert calcular_graus_hora(no_piso, 10.0, 13.0) == (0.0, 0.0)
    assert calcular_graus_hora(no_teto, 10.0, 13.0) == (0.0, 0.0)


def test_calor_e_frio_sao_somados_separados():
    # Calor: excesso 0, 2 e 0 -> media 1 por 3 h + media 1 por 4 h = 7
    # Frio: excesso 0, 0 e 1 -> media 0 por 3 h + media 0,5 por 4 h = 2
    leituras = [leitura(0, 11.0), leitura(3, 15.0), leitura(7, 9.0)]
    assert calcular_graus_hora(leituras, 10.0, 13.0) == (7.0, 2.0)


def test_nivel_do_lote_e_o_pior_dos_dois_lados():
    assert nivel_mais_grave("VERDE", "LARANJA") == "LARANJA"
    assert nivel_mais_grave("VERMELHO", "AMARELO") == "VERMELHO"
    assert nivel_mais_grave("VERDE", "VERDE") == "VERDE"


def test_calor_continua_classificado_como_antes():
    # Mesmo caso da analise completa: so calor, 30 graus-hora -> LARANJA
    leituras = [leitura(0, 1.0), leitura(10, 5.0), leitura(20, 1.0)]
    analise = analisar_lote(leituras, FAIXA_UVA)
    assert analise["nivel_acima"] == "LARANJA"
    assert analise["nivel_abaixo"] == "VERDE"
    assert analise["nivel"] == "LARANJA"


def test_trechos_fora_da_faixa_separam_calor_e_frio():
    leituras = [
        leitura(0, 11.0),    # dentro
        leitura(1, 14.0),    # acima
        leitura(2, 15.5),    # acima (mais quente)
        leitura(3, 9.0),     # abaixo: troca de lado, novo trecho
        leitura(4, 8.0),     # abaixo (mais frio)
        leitura(5, 12.0),    # dentro: fecha o trecho
    ]
    trechos = detectar_trechos_fora_da_faixa(leituras, 10.0, 13.0)
    assert len(trechos) == 2
    assert trechos[0]["lado"] == "acima"
    assert trechos[0]["temp_extrema_c"] == 15.5
    assert trechos[0]["duracao_min"] == 60.0
    assert trechos[1]["lado"] == "abaixo"
    assert trechos[1]["temp_extrema_c"] == 8.0


def test_lote_sem_leituras_tem_os_tres_niveis_sem_dados():
    analise = analisar_lote([], FAIXA_MANGA)
    assert analise["nivel_acima"] == "SEM_DADOS"
    assert analise["nivel_abaixo"] == "SEM_DADOS"
    assert analise["trechos_fora_faixa"] == []
