"""
Testes de casos de borda da API: faixa com Infinity/NaN, conta dos graus-hora,
selo com poucos dados, respostas estranhas do ThingSpeak, canal com muitas
leituras, datas do lote, umidade e luz invalidas e CORS.
"""

import json
from datetime import datetime, timedelta, timezone

import config
from auxiliares import (
    INICIO,
    corpo_de_lote,
    criar_lote,
    criar_lote_encerrado_com,
    em,
    encerrar_lote,
    faixa_da_uva,
    fruta_melao,
    gravar_leituras,
    leitura_do_thingspeak,
    leituras_do_lote,
    nova_leitura,
    sem_campo,
    thingspeak_devolve,
)
from services import thingspeak
from services.analise import calcular_graus_hora

MENSAGEM_THINGSPEAK = {
    "erro": "Não foi possível ler os dados do ThingSpeak agora. Tente de novo em alguns minutos."
}


# ---------- funcoes auxiliares deste arquivo ----------

def enviar_json_bruto(cliente, metodo, rota, corpo):
    """Envia o corpo com json.dumps, que escreve Infinity e NaN (o httpx recusaria)."""
    cabecalho = {"Content-Type": "application/json"}
    return cliente.request(metodo, rota, content=json.dumps(corpo), headers=cabecalho)


def leituras_a_cada_30_min(horas, temperatura=1.0):
    """Leituras de 30 em 30 minutos, do inicio do lote ate 'horas' depois."""
    leituras = []
    for meia_hora in range(0, horas * 2 + 1):
        leituras.append(nova_leitura(em(0, meia_hora * 30), temperatura))
    return leituras


def selo_do_lote(cliente, lote):
    return cliente.get(f"/api/publico/{lote['codigo_publico']}").json()["selo_faixa_segura"]


class RespostaFalsa:
    """Imita a resposta do requests.get com o corpo JSON escolhido pelo teste."""

    def __init__(self, corpo):
        self.corpo = corpo

    def raise_for_status(self):
        pass

    def json(self):
        return self.corpo


def thingspeak_responde(monkeypatch, corpo):
    """Faz o requests.get devolver sempre o mesmo corpo, sem internet."""

    def get_falso(*args, **kwargs):
        return RespostaFalsa(corpo)

    monkeypatch.setattr(thingspeak.requests, "get", get_falso)


def canal_falso(monkeypatch, entradas):
    """
    Imita o canal real (conferido no canal 3493443): filtra por start e end,
    inclusive e em UTC, e devolve as 'results' entradas mais recentes, em ordem.
    Devolve a lista de parametros de cada chamada, para o teste conferir.
    """
    chamadas = []

    def get_falso(url, params, timeout):
        chamadas.append(params)
        selecionadas = []
        for entrada in entradas:
            # As datas sao comparadas como texto: nesse formato (ano, mes, dia,
            # hora...), a ordem do texto e a ordem do tempo.
            data = entrada["created_at"].replace("T", " ").replace("Z", "")
            if "start" in params and data < params["start"]:
                continue
            if "end" in params and data > params["end"]:
                continue
            selecionadas.append(entrada)
        # [-n:] pega as n ultimas da lista, ou seja, as mais recentes.
        return RespostaFalsa({"feeds": selecionadas[-params["results"]:]})

    monkeypatch.setattr(thingspeak.requests, "get", get_falso)
    return chamadas


def entrada_do_canal(entry_id, data, temperatura=1.0, umidade="90.0", lux=None):
    """Entrada no formato do ThingSpeak: campos numericos vem como texto."""
    return {
        "entry_id": entry_id,
        "created_at": data.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "field1": str(temperatura),
        "field2": umidade,
        "field5": lux,
    }


# ---------- 1. Infinity e NaN na faixa segura ----------

def test_lote_com_teto_infinito_devolve_400_e_nao_quebra_a_lista(cliente):
    corpo = corpo_de_lote(faixa_segura=faixa_da_uva(temp_max_c=float("inf")))
    resposta = enviar_json_bruto(cliente, "POST", "/api/lotes", corpo)
    assert resposta.status_code == 400
    assert cliente.get("/api/lotes").status_code == 200


def test_lote_com_piso_nan_devolve_400(cliente):
    corpo = corpo_de_lote(faixa_segura=faixa_da_uva(temp_min_c=float("nan")))
    resposta = enviar_json_bruto(cliente, "POST", "/api/lotes", corpo)
    assert resposta.status_code == 400
    assert cliente.get("/api/lotes").status_code == 200


def test_editar_fruta_com_teto_infinito_devolve_400_e_nao_quebra_a_lista(cliente):
    corpo = sem_campo(fruta_melao(temp_max_c=float("inf")), "id")
    resposta = enviar_json_bruto(cliente, "PUT", "/api/frutas/uva", corpo)
    assert resposta.status_code == 400
    assert cliente.get("/api/frutas").status_code == 200


def test_umidade_nan_devolve_400(cliente):
    corpo = sem_campo(fruta_melao(umidade_max_pct=float("nan")), "id")
    resposta = enviar_json_bruto(cliente, "PUT", "/api/frutas/uva", corpo)
    assert resposta.status_code == 400


def test_faixa_fora_do_limite_fisico_do_sensor_devolve_400(cliente):
    # A analise so aceita leituras de -40 a 80 °C; uma faixa alem disso nao faz sentido.
    abaixo = corpo_de_lote(faixa_segura=faixa_da_uva(temp_min_c=-41.0))
    acima = corpo_de_lote(faixa_segura=faixa_da_uva(temp_max_c=81.0))
    assert cliente.post("/api/lotes", json=abaixo).status_code == 400
    assert cliente.post("/api/lotes", json=acima).status_code == 400


# ---------- 2a. graus-hora pela media das duas pontas do intervalo ----------

def test_calor_nao_depende_da_ordem_das_leituras():
    # Excesso de 28 e de 0: media 14 °C durante 10 h = 140 °C·h, nos dois sentidos.
    esfriando = [nova_leitura(em(0), 30.0), nova_leitura(em(10), 1.0)]
    esquentando = [nova_leitura(em(0), 1.0), nova_leitura(em(10), 30.0)]
    assert calcular_graus_hora(esfriando, 0.0, 2.0) == (140.0, 0.0)
    assert calcular_graus_hora(esquentando, 0.0, 2.0) == (140.0, 0.0)


def test_frio_nao_depende_da_ordem_das_leituras():
    # Manga: excesso de 5 e de 0 abaixo do piso: media 2,5 °C durante 10 h = 25 °C·h.
    esquentando = [nova_leitura(em(0), 5.0), nova_leitura(em(10), 12.0)]
    esfriando = [nova_leitura(em(0), 12.0), nova_leitura(em(10), 5.0)]
    assert calcular_graus_hora(esquentando, 10.0, 13.0) == (0.0, 25.0)
    assert calcular_graus_hora(esfriando, 10.0, 13.0) == (0.0, 25.0)


def test_lote_que_esfria_de_30_para_1_grau_nao_fica_verde(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [nova_leitura(em(0), 30.0), nova_leitura(em(10), 1.0)])
    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["graus_hora_acima"] == 140.0
    assert analise["nivel"] == "VERMELHO"


# ---------- 2b. selo exige leituras suficientes e nenhum buraco ----------

def test_uma_leitura_so_de_40_graus_nao_ganha_selo(cliente, banco):
    leituras = [nova_leitura(em(0), 40.0)]
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T09:05:00Z")
    assert selo_do_lote(cliente, lote) is False


def test_nove_leituras_nao_bastam_para_o_selo(cliente, banco):
    leituras = []
    for minuto in range(0, 9):
        leituras.append(nova_leitura(em(0, minuto), 1.0))
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T09:08:00Z")
    assert selo_do_lote(cliente, lote) is False


def test_dez_leituras_sem_buraco_ganham_o_selo(cliente, banco):
    leituras = []
    for minuto in range(0, 10):
        leituras.append(nova_leitura(em(0, minuto), 1.0))
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T09:09:00Z")
    assert selo_do_lote(cliente, lote) is True


def test_leituras_de_30_em_30_minutos_ganham_o_selo(cliente, banco):
    leituras = leituras_a_cada_30_min(10)
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T19:00:00Z")
    assert selo_do_lote(cliente, lote) is True


def test_buraco_no_meio_da_viagem_tira_o_selo(cliente, banco):
    # Tira a leitura das 5 h: buraco de 1 h entre 4h30 e 5h30.
    leituras = leituras_a_cada_30_min(10)
    del leituras[10]
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T19:00:00Z")
    assert selo_do_lote(cliente, lote) is False


def test_buraco_no_fim_da_viagem_tira_o_selo(cliente, banco):
    # Leituras so nas primeiras 5 h de uma viagem de 10 h.
    leituras = leituras_a_cada_30_min(5)
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T19:00:00Z")
    assert selo_do_lote(cliente, lote) is False


def test_buraco_no_comeco_da_viagem_tira_o_selo(cliente, banco):
    # Primeira leitura so 1 h depois do inicio do lote.
    leituras = leituras_a_cada_30_min(10)[2:]
    lote = criar_lote_encerrado_com(cliente, banco, leituras, "2026-10-24T19:00:00Z")
    assert selo_do_lote(cliente, lote) is False


def test_selo_aparece_quando_as_leituras_atrasadas_chegam(cliente, monkeypatch):
    # O lote chegou sem nenhuma leitura; elas vem depois, com o horario da medicao.
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T14:00:00Z")
    assert selo_do_lote(cliente, lote) is False

    leituras = []
    for meia_hora in range(0, 11):
        data = em(0, meia_hora * 30).replace(tzinfo=timezone.utc)
        leituras.append(leitura_do_thingspeak(meia_hora + 1, data, 1.0))
    thingspeak_devolve(monkeypatch, leituras)
    cliente.post("/api/sincronizar")
    assert selo_do_lote(cliente, lote) is True


# ---------- 3. respostas estranhas do ThingSpeak viram 502 ----------

def test_corpo_que_nao_e_objeto_devolve_502(cliente, monkeypatch):
    # O ThingSpeak responde -1 quando a chave do canal esta errada.
    for corpo in [-1, [], "erro", None, {"feeds": None}, {"feeds": "erro"}]:
        thingspeak_responde(monkeypatch, corpo)
        resposta = cliente.post("/api/sincronizar")
        assert resposta.status_code == 502, corpo
        assert resposta.json() == MENSAGEM_THINGSPEAK


def test_corpo_sem_feeds_devolve_502(cliente, monkeypatch):
    thingspeak_responde(monkeypatch, {"status": "0"})
    assert cliente.post("/api/sincronizar").status_code == 502


def test_entrada_sem_data_ou_sem_entry_id_devolve_502(cliente, monkeypatch):
    entradas_ruins = [
        {"entry_id": 1, "created_at": None, "field1": "1.0"},
        {"entry_id": 1, "field1": "1.0"},
        {"entry_id": 1, "created_at": "ontem", "field1": "1.0"},
        {"created_at": "2026-10-24T09:00:00Z", "field1": "1.0"},
        {"entry_id": None, "created_at": "2026-10-24T09:00:00Z", "field1": "1.0"},
        "nao e uma entrada",
    ]
    for entrada in entradas_ruins:
        thingspeak_responde(monkeypatch, {"feeds": [entrada]})
        resposta = cliente.post("/api/sincronizar")
        assert resposta.status_code == 502, entrada
        assert resposta.json() == MENSAGEM_THINGSPEAK


def test_campo_que_nao_e_numero_vira_nulo_em_vez_de_erro(cliente, monkeypatch):
    # Temperatura invalida descarta a leitura; o servico nao pode quebrar.
    entrada = {"entry_id": 1, "created_at": "2026-10-24T09:00:00Z", "field1": []}
    thingspeak_responde(monkeypatch, {"feeds": [entrada]})
    resposta = cliente.post("/api/sincronizar")
    assert resposta.status_code == 200
    assert resposta.json()["descartadas"] == 1


# ---------- 4. leituras antigas nao se perdem ----------

def test_canal_com_mais_de_8000_leituras_traz_todas(monkeypatch):
    # 8000 e o maximo por consulta; a 20 s por leitura sao so cerca de 44 h.
    entradas = []
    for numero in range(0, 17000):
        entradas.append(entrada_do_canal(numero + 1, INICIO + timedelta(seconds=20 * numero)))
    chamadas = canal_falso(monkeypatch, entradas)

    leituras = thingspeak.buscar_leituras(3493443)

    assert len(leituras) == 17000
    assert len(chamadas) == 3


def test_sincronizar_com_banco_vazio_nao_pede_data_inicial(cliente, monkeypatch):
    chamadas = canal_falso(monkeypatch, [entrada_do_canal(1, em(0))])
    cliente.post("/api/sincronizar")
    assert "start" not in chamadas[0]


def test_sincronizar_busca_desde_a_ultima_leitura_menos_a_margem_de_atraso(cliente, monkeypatch):
    canal_falso(monkeypatch, [entrada_do_canal(1, datetime(2026, 10, 24, 9, 0, 0))])
    cliente.post("/api/sincronizar")

    chamadas = canal_falso(monkeypatch, [])
    cliente.post("/api/sincronizar")
    # Ultima leitura em 24/10 09:00, menos 7 dias de margem, em UTC.
    assert chamadas[0]["start"] == "2026-10-17 09:00:00"


def test_leitura_atrasada_mais_antiga_que_a_ultima_gravada_nao_se_perde(cliente, monkeypatch):
    lote = criar_lote(cliente)
    recente = entrada_do_canal(1, em(10), temperatura=5.0)
    canal_falso(monkeypatch, [recente])
    cliente.post("/api/sincronizar")

    # A leitura das 5 h chega depois, com entry_id maior e o horario da medicao.
    atrasada = entrada_do_canal(2, em(5), temperatura=5.0)
    canal_falso(monkeypatch, [atrasada, recente])
    resposta = cliente.post("/api/sincronizar")

    assert resposta.json()["novas"] == 1
    assert len(leituras_do_lote(cliente, lote)) == 2


# ---------- 5. datas do lote ----------

def test_inicio_antes_do_fim_do_ultimo_lote_devolve_400(cliente):
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro, fim="2026-10-24T20:00:00Z")

    corpo = corpo_de_lote(inicio="2026-10-24T19:00:00Z")
    resposta = cliente.post("/api/lotes", json=corpo)

    assert resposta.status_code == 400
    assert resposta.json() == {
        "erro": f"O início precisa ser depois do fim do lote {primeiro['id']}."
    }


def test_inicio_igual_ao_fim_do_ultimo_lote_devolve_400(cliente):
    # A leitura desse instante ficaria nos dois lotes.
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro, fim="2026-10-24T20:00:00Z")
    corpo = corpo_de_lote(inicio="2026-10-24T20:00:00Z")
    assert cliente.post("/api/lotes", json=corpo).status_code == 400


def test_inicio_depois_do_fim_do_ultimo_lote_e_aceito(cliente):
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro, fim="2026-10-24T20:00:00Z")
    corpo = corpo_de_lote(inicio="2026-10-24T20:00:01Z")
    assert cliente.post("/api/lotes", json=corpo).status_code == 201


def test_fim_no_futuro_devolve_400(cliente):
    lote = criar_lote(cliente)
    amanha = datetime.now(timezone.utc) + timedelta(days=1)
    resposta = encerrar_lote(cliente, lote, fim=amanha.strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert resposta.status_code == 400
    assert resposta.json() == {"erro": "O fim não pode estar no futuro."}


# ---------- 6. umidade e luz fora de faixa viram vazio ----------

def test_umidade_e_luz_invalidas_viram_nulo_e_nao_quebram_as_leituras(cliente, monkeypatch):
    lote = criar_lote(cliente)
    entradas = [
        entrada_do_canal(1, em(1), umidade="1e999", lux="1e999"),
        entrada_do_canal(2, em(2), umidade="nan", lux="nan"),
        entrada_do_canal(3, em(3), umidade="150", lux="-5"),
        entrada_do_canal(4, em(4), umidade="88.5", lux="12"),
    ]
    canal_falso(monkeypatch, entradas)
    assert cliente.post("/api/sincronizar").json()["novas"] == 4

    resposta = cliente.get(f"/api/lotes/{lote['id']}/leituras")
    assert resposta.status_code == 200
    leituras = resposta.json()
    for leitura in leituras[:3]:
        assert leitura["umidade_pct"] is None
        assert leitura["luminosidade_lux"] is None
    assert leituras[3]["umidade_pct"] == 88.5
    assert leituras[3]["luminosidade_lux"] == 12.0


# ---------- 7. CORS ----------

def test_origens_do_cors_sem_espacos_e_sem_itens_vazios():
    texto = " http://localhost:5500 , http://127.0.0.1:5500,"
    assert config.separar_origens(texto) == ["http://localhost:5500", "http://127.0.0.1:5500"]
