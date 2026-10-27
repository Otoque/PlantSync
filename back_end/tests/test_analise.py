from datetime import datetime, timedelta

from services.analise import (
    analisar_lote,
    calcular_graus_hora,
    classificar_risco,
    detectar_eventos_porta,
    limpar_leituras,
)

FAIXA_UVA = {"temp_min_c": 0.0, "temp_max_c": 2.0, "umidade_min_pct": 85.0, "umidade_max_pct": 95.0}
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
    assert calcular_graus_hora(leituras, 2.0) == 0.0


def test_graus_hora_soma_excesso_vezes_tempo():
    # 2 graus acima do limite durante 3 horas = 6 graus-hora
    leituras = [leitura(0, 2.0), leitura(1, 4.0), leitura(2, 4.0), leitura(3, 4.0)]
    assert calcular_graus_hora(leituras, 2.0) == 6.0


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
    assert analise["graus_hora"] == 30.0
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
