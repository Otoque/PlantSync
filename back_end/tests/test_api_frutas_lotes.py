"""
Testes de caixa-preta da API (frutas, lotes e leituras), escritos a partir de
docs/api-contrato.md. Os testes so usam o que o contrato promete.
"""

from datetime import datetime, timedelta, timezone

from app import app
from models.banco import abrir_sessao
from models.tabelas import Leitura

INICIO = datetime(2026, 10, 24, 9, 0, 0)  # 24/10/2026 09:00 UTC

FRUTA_MELAO = {
    "id": "melao",
    "nome": "Melão",
    "temp_min_c": 2.0,
    "temp_max_c": 5.0,
    "umidade_min_pct": 90.0,
    "umidade_max_pct": 95.0,
    "fonte": "Referência da faixa",
}

LOTE_UVA = {
    "fruta": "uva",
    "origem": "Packing house Petrolina",
    "porto_destino": "Suape",
    "inicio": "2026-10-24T09:00:00Z",
}


# ---------- funcoes auxiliares ----------

def criar_lote(cliente, **mudancas):
    corpo = {**LOTE_UVA, **mudancas}
    resposta = cliente.post("/api/lotes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def agora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gravar_leituras(leituras):
    """
    Grava leituras direto no banco de teste (a mesma sessao que a API usa).
    Cada item e (horas apos o INICIO, temperatura, umidade, luminosidade).
    """
    sessao = next(app.dependency_overrides[abrir_sessao]())
    for numero, (horas, temperatura, umidade, lux) in enumerate(leituras, start=1):
        sessao.add(Leitura(
            entry_id=numero,
            data_hora=INICIO + timedelta(hours=horas),
            temperatura_c=temperatura,
            umidade_pct=umidade,
            luminosidade_lux=lux,
        ))
    sessao.commit()
    sessao.close()


def achar_datas(valor):
    """Percorre o JSON e devolve os textos dos campos que sao datas."""
    textos = []
    if isinstance(valor, dict):
        for chave, conteudo in valor.items():
            if chave in ("inicio", "fim", "data_hora", "primeira_leitura", "ultima_leitura") and conteudo:
                textos.append(conteudo)
            textos += achar_datas(conteudo)
    elif isinstance(valor, list):
        for item in valor:
            textos += achar_datas(item)
    return textos


# ---------- saude e frutas ----------

def test_saude_devolve_status_ok(cliente):
    resposta = cliente.get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_listar_frutas_traz_uva_e_manga_iniciais(cliente):
    resposta = cliente.get("/api/frutas")
    assert resposta.status_code == 200
    frutas = {f["id"]: f for f in resposta.json()}

    assert set(frutas) == {"uva", "manga"}
    assert frutas["uva"]["temp_min_c"] == 0.0
    assert frutas["uva"]["temp_max_c"] == 2.0
    assert frutas["uva"]["umidade_min_pct"] == 85.0
    assert frutas["uva"]["umidade_max_pct"] == 95.0
    assert frutas["manga"]["temp_min_c"] == 10.0
    assert frutas["manga"]["temp_max_c"] == 13.0
    assert frutas["manga"]["umidade_min_pct"] == 85.0
    assert frutas["manga"]["umidade_max_pct"] == 90.0


def test_cadastrar_fruta_valida_devolve_201_e_aparece_na_lista(cliente):
    resposta = cliente.post("/api/frutas", json=FRUTA_MELAO)
    assert resposta.status_code == 201
    assert resposta.json() == FRUTA_MELAO

    ids = [f["id"] for f in cliente.get("/api/frutas").json()]
    assert "melao" in ids


def test_cadastrar_fruta_com_id_repetido_devolve_400(cliente):
    cliente.post("/api/frutas", json=FRUTA_MELAO)
    resposta = cliente.post("/api/frutas", json=FRUTA_MELAO)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_cadastrar_fruta_com_id_de_fruta_inicial_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "id": "uva"})
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_temp_min_igual_a_temp_max_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "temp_min_c": 5.0, "temp_max_c": 5.0})
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_cadastrar_fruta_com_temp_min_maior_que_temp_max_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "temp_min_c": 8.0, "temp_max_c": 5.0})
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_min_maior_que_max_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "umidade_min_pct": 96.0, "umidade_max_pct": 90.0})
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_acima_de_100_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "umidade_max_pct": 101.0})
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_abaixo_de_0_devolve_400(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "umidade_min_pct": -1.0})
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_id_invalido_devolve_400(cliente):
    # o id so aceita letras minusculas sem acento, numeros, - ou _
    for id_ruim in ["Melao", "melão", "meu melao", "melao!"]:
        resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "id": id_ruim})
        assert resposta.status_code == 400, id_ruim


def test_cadastrar_fruta_aceita_id_com_hifen_underline_e_numero(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "id": "melao-2_b"})
    assert resposta.status_code == 201


def test_cadastrar_fruta_sem_campo_obrigatorio_devolve_400(cliente):
    corpo = dict(FRUTA_MELAO)
    del corpo["fonte"]
    resposta = cliente.post("/api/frutas", json=corpo)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_erro_de_fruta_segue_o_formato_com_chave_erro(cliente):
    resposta = cliente.post("/api/frutas", json={**FRUTA_MELAO, "temp_min_c": 9.0, "temp_max_c": 5.0})
    corpo = resposta.json()
    assert list(corpo.keys()) == ["erro"]
    assert isinstance(corpo["erro"], str)
    assert corpo["erro"] != ""


def test_editar_fruta_devolve_200_com_os_novos_valores(cliente):
    corpo = {k: v for k, v in FRUTA_MELAO.items() if k != "id"}
    corpo["nome"] = "Uva sem semente"
    corpo["temp_min_c"] = 0.0
    corpo["temp_max_c"] = 4.0

    resposta = cliente.put("/api/frutas/uva", json=corpo)
    assert resposta.status_code == 200
    assert resposta.json()["id"] == "uva"
    assert resposta.json()["nome"] == "Uva sem semente"
    assert resposta.json()["temp_max_c"] == 4.0

    uva = [f for f in cliente.get("/api/frutas").json() if f["id"] == "uva"][0]
    assert uva["temp_max_c"] == 4.0


def test_editar_fruta_inexistente_devolve_404(cliente):
    corpo = {k: v for k, v in FRUTA_MELAO.items() if k != "id"}
    resposta = cliente.put("/api/frutas/abacaxi", json=corpo)
    assert resposta.status_code == 404
    assert "erro" in resposta.json()


def test_editar_fruta_com_faixa_invalida_devolve_400(cliente):
    corpo = {k: v for k, v in FRUTA_MELAO.items() if k != "id"}
    corpo["temp_min_c"] = 9.0
    corpo["temp_max_c"] = 5.0
    resposta = cliente.put("/api/frutas/uva", json=corpo)
    assert resposta.status_code == 400


# ---------- criar lote ----------

def test_criar_lote_devolve_201_em_transito_com_faixa_da_fruta(cliente):
    resposta = cliente.post("/api/lotes", json=LOTE_UVA)
    assert resposta.status_code == 201
    lote = resposta.json()

    assert lote["fruta"] == "uva"
    assert lote["origem"] == "Packing house Petrolina"
    assert lote["porto_destino"] == "Suape"
    assert lote["inicio"] == "2026-10-24T09:00:00Z"
    assert lote["fim"] is None
    assert lote["status"] == "em_transito"
    assert lote["faixa_segura"] == {
        "temp_min_c": 0.0,
        "temp_max_c": 2.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 95.0,
    }
    assert lote["risco"]["nivel"] == "SEM_DADOS"
    assert lote["risco"]["graus_hora"] == 0


def test_criar_lote_sem_inicio_usa_o_horario_atual(cliente):
    corpo = {k: v for k, v in LOTE_UVA.items() if k != "inicio"}
    antes = agora_utc() - timedelta(minutes=1)
    resposta = cliente.post("/api/lotes", json=corpo)
    depois = agora_utc() + timedelta(minutes=1)

    assert resposta.status_code == 201
    inicio = datetime.strptime(resposta.json()["inicio"], "%Y-%m-%dT%H:%M:%SZ")
    assert antes <= inicio <= depois


def test_criar_lote_com_fruta_inexistente_devolve_400(cliente):
    resposta = cliente.post("/api/lotes", json={**LOTE_UVA, "fruta": "abacaxi"})
    assert resposta.status_code == 400
    assert "abacaxi" in resposta.json()["erro"]


def test_criar_lote_sem_origem_devolve_400(cliente):
    corpo = {k: v for k, v in LOTE_UVA.items() if k != "origem"}
    resposta = cliente.post("/api/lotes", json=corpo)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_criar_lote_sem_porto_destino_devolve_400(cliente):
    corpo = {k: v for k, v in LOTE_UVA.items() if k != "porto_destino"}
    resposta = cliente.post("/api/lotes", json=corpo)
    assert resposta.status_code == 400


def test_segundo_lote_em_transito_devolve_400_citando_o_lote_aberto(cliente):
    primeiro = criar_lote(cliente)
    resposta = cliente.post("/api/lotes", json={**LOTE_UVA, "fruta": "manga"})
    assert resposta.status_code == 400
    assert f"lote {primeiro['id']}" in resposta.json()["erro"]


def test_depois_de_encerrar_o_lote_e_possivel_criar_outro(cliente):
    primeiro = criar_lote(cliente)
    cliente.post(f"/api/lotes/{primeiro['id']}/encerrar")
    resposta = cliente.post("/api/lotes", json={**LOTE_UVA, "fruta": "manga"})
    assert resposta.status_code == 201


def test_criar_lote_com_faixa_segura_propria(cliente):
    faixa = {"temp_min_c": 1.0, "temp_max_c": 3.0, "umidade_min_pct": 80.0, "umidade_max_pct": 92.0}
    lote = criar_lote(cliente, faixa_segura=faixa)
    assert lote["faixa_segura"] == faixa

    # a fruta continua com a faixa original
    uva = [f for f in cliente.get("/api/frutas").json() if f["id"] == "uva"][0]
    assert uva["temp_max_c"] == 2.0


def test_criar_lote_com_faixa_segura_propria_invalida_devolve_400(cliente):
    faixa = {"temp_min_c": 5.0, "temp_max_c": 3.0, "umidade_min_pct": 80.0, "umidade_max_pct": 92.0}
    resposta = cliente.post("/api/lotes", json={**LOTE_UVA, "faixa_segura": faixa})
    assert resposta.status_code == 400


def test_criar_lote_com_faixa_segura_de_umidade_acima_de_100_devolve_400(cliente):
    faixa = {"temp_min_c": 0.0, "temp_max_c": 3.0, "umidade_min_pct": 80.0, "umidade_max_pct": 120.0}
    resposta = cliente.post("/api/lotes", json={**LOTE_UVA, "faixa_segura": faixa})
    assert resposta.status_code == 400


def test_editar_fruta_depois_nao_muda_a_faixa_do_lote_ja_criado(cliente):
    lote = criar_lote(cliente)

    corpo = {
        "nome": "Uva de mesa",
        "temp_min_c": 0.0,
        "temp_max_c": 4.0,
        "umidade_min_pct": 70.0,
        "umidade_max_pct": 99.0,
        "fonte": "Outra fonte",
    }
    assert cliente.put("/api/frutas/uva", json=corpo).status_code == 200

    detalhe = cliente.get(f"/api/lotes/{lote['id']}").json()
    assert detalhe["faixa_segura"]["temp_max_c"] == 2.0
    assert detalhe["faixa_segura"]["umidade_min_pct"] == 85.0

    item_da_lista = cliente.get("/api/lotes").json()[0]
    assert item_da_lista["faixa_segura"]["temp_max_c"] == 2.0


def test_editar_fruta_depois_nao_muda_o_risco_do_lote_ja_criado(cliente):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h
    gravar_leituras([(h, 5.0, 90.0, None) for h in range(0, 11)])

    corpo = {
        "nome": "Uva de mesa",
        "temp_min_c": 0.0,
        "temp_max_c": 10.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 95.0,
        "fonte": "Outra fonte",
    }
    cliente.put("/api/frutas/uva", json=corpo)

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["graus_hora"] == 30.0
    assert analise["amostras_fora_faixa"] == 11


def test_editar_fruta_vale_para_o_lote_novo(cliente):
    primeiro = criar_lote(cliente)
    cliente.post(f"/api/lotes/{primeiro['id']}/encerrar")

    corpo = {
        "nome": "Uva de mesa",
        "temp_min_c": 0.0,
        "temp_max_c": 4.0,
        "umidade_min_pct": 85.0,
        "umidade_max_pct": 95.0,
        "fonte": "Outra fonte",
    }
    cliente.put("/api/frutas/uva", json=corpo)

    novo = criar_lote(cliente)
    assert novo["faixa_segura"]["temp_max_c"] == 4.0


# ---------- listar lotes ----------

def test_listar_lotes_vazio_devolve_lista_vazia(cliente):
    resposta = cliente.get("/api/lotes")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_listar_lotes_do_mais_recente_para_o_mais_antigo(cliente):
    antigo = criar_lote(cliente, inicio="2026-10-20T09:00:00Z")
    cliente.post(f"/api/lotes/{antigo['id']}/encerrar", json={"fim": "2026-10-21T09:00:00Z"})
    recente = criar_lote(cliente, inicio="2026-10-24T09:00:00Z")

    ids = [lote["id"] for lote in cliente.get("/api/lotes").json()]
    assert ids == [recente["id"], antigo["id"]]


def test_listar_lotes_traz_resumo_de_risco(cliente):
    criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h
    gravar_leituras([(h, 5.0, 90.0, None) for h in range(0, 11)])

    lote = cliente.get("/api/lotes").json()[0]
    assert lote["risco"]["graus_hora"] == 30.0
    assert lote["risco"]["nivel"] == "LARANJA"


# ---------- detalhe do lote ----------

def test_detalhe_de_lote_inexistente_devolve_404(cliente):
    resposta = cliente.get("/api/lotes/99")
    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "Lote 99 não encontrado."}


def test_detalhe_de_lote_sem_leituras(cliente):
    lote = criar_lote(cliente)
    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]

    assert analise["amostras"] == 0
    assert analise["amostras_fora_faixa"] == 0
    assert analise["nivel"] == "SEM_DADOS"
    assert analise["primeira_leitura"] is None
    assert analise["ultima_leitura"] is None
    assert analise["temp_min_c"] is None
    assert analise["temp_max_c"] is None
    assert analise["temp_media_c"] is None
    assert analise["eventos_porta"] == []


def test_detalhe_do_lote_calcula_graus_hora_e_nivel(cliente):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h -> LARANJA (20 a menos de 50)
    gravar_leituras([(h, 5.0, 90.0, None) for h in range(0, 11)])

    detalhe = cliente.get(f"/api/lotes/{lote['id']}").json()
    analise = detalhe["analise"]

    assert detalhe["id"] == lote["id"]
    assert analise["amostras"] == 11
    assert analise["graus_hora"] == 30.0
    assert analise["nivel"] == "LARANJA"
    assert analise["recomendacao"] == "Abuso relevante. Inspeção física obrigatória antes do embarque."
    assert analise["temp_min_c"] == 5.0
    assert analise["temp_max_c"] == 5.0
    assert analise["temp_media_c"] == 5.0
    assert analise["primeira_leitura"] == "2026-10-24T09:00:00Z"
    assert analise["ultima_leitura"] == "2026-10-24T19:00:00Z"


def test_detalhe_do_lote_nivel_verde_quando_tudo_dentro_da_faixa(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([(h, 1.0, 90.0, None) for h in range(0, 5)])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["graus_hora"] == 0
    assert analise["nivel"] == "VERDE"
    assert analise["amostras_fora_faixa"] == 0


def test_detalhe_do_lote_nivel_vermelho_com_50_graus_hora(cliente):
    lote = criar_lote(cliente)
    # 5 °C acima do limite (2 °C) por 10 h = 50 °C·h -> VERMELHO (50 ou mais)
    gravar_leituras([(h, 7.0, 90.0, None) for h in range(0, 11)])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["graus_hora"] == 50.0
    assert analise["nivel"] == "VERMELHO"


def test_amostras_fora_da_faixa_contam_temperatura_acima_e_abaixo(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, None),   # dentro
        (1, 5.0, 90.0, None),   # acima de 2 °C
        (2, -1.0, 90.0, None),  # abaixo de 0 °C
        (3, 2.0, 90.0, None),   # no limite: ainda dentro
        (4, 0.0, 90.0, None),   # no limite: ainda dentro
    ])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras"] == 5
    assert analise["amostras_fora_faixa"] == 2


def test_umidade_fora_da_faixa_nao_entra_em_amostras_fora_faixa(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 50.0, None),   # umidade baixa, temperatura boa
        (1, 1.0, 99.0, None),   # umidade alta, temperatura boa
        (2, 1.0, 90.0, None),
    ])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras_fora_faixa"] == 0


def test_detalhe_do_lote_traz_eventos_de_porta(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0.0, 1.0, 90.0, 5.0),
        (12.0, 1.0, 90.0, 640.0),   # porta abre
        (12.5, 1.0, 90.0, 880.0),
        (13.0, 1.0, 90.0, 700.0),   # porta ainda aberta
        (14.0, 1.0, 90.0, 5.0),     # fecha
    ])

    eventos = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]["eventos_porta"]
    assert len(eventos) == 1
    assert eventos[0]["inicio"] == "2026-10-24T21:00:00Z"
    assert eventos[0]["fim"] == "2026-10-24T22:00:00Z"
    assert eventos[0]["duracao_min"] == 60.0
    assert eventos[0]["lux_max"] == 880.0


def test_dois_eventos_de_porta_separados_viram_dois_eventos(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, 500.0),
        (1, 1.0, 90.0, 5.0),
        (2, 1.0, 90.0, 500.0),
    ])

    eventos = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]["eventos_porta"]
    assert len(eventos) == 2


def test_luminosidade_de_300_lux_nao_e_porta_aberta(cliente):
    lote = criar_lote(cliente)
    # o contrato diz "passa de 300 lux": 300 exatos nao conta
    gravar_leituras([(0, 1.0, 90.0, 300.0), (1, 1.0, 90.0, 300.0)])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["eventos_porta"] == []


def test_leitura_antes_do_inicio_do_lote_nao_entra(cliente):
    lote = criar_lote(cliente)  # inicio as 09:00
    gravar_leituras([
        (-2, 20.0, 90.0, None),  # 07:00, antes do lote
        (0, 1.0, 90.0, None),
        (1, 1.0, 90.0, None),
    ])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["primeira_leitura"] == "2026-10-24T09:00:00Z"
    assert analise["graus_hora"] == 0


def test_leituras_depois_do_fim_do_lote_nao_entram(cliente):
    lote = criar_lote(cliente)
    cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-24T12:00:00Z"})
    gravar_leituras([
        (0, 1.0, 90.0, None),
        (3, 1.0, 90.0, None),    # 12:00, no fim
        (4, 30.0, 90.0, None),   # 13:00, depois do fim
        (5, 30.0, 90.0, None),
    ])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["graus_hora"] == 0
    assert analise["ultima_leitura"] == "2026-10-24T12:00:00Z"


def test_lote_em_transito_recebe_tudo_o_que_chegar_depois_do_inicio(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([(0, 1.0, 90.0, None), (100, 1.0, 90.0, None)])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras"] == 2


def test_leitura_com_temperatura_impossivel_nao_entra_na_analise(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, None),
        (1, 999.0, 90.0, None),   # acima de 80 °C
        (2, -50.0, 90.0, None),   # abaixo de -40 °C
        (3, 1.0, 90.0, None),
    ])

    analise = cliente.get(f"/api/lotes/{lote['id']}").json()["analise"]
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["graus_hora"] == 0


# ---------- encerrar ----------

def test_encerrar_sem_corpo_usa_o_horario_atual(cliente):
    lote = criar_lote(cliente)
    antes = agora_utc() - timedelta(minutes=1)
    resposta = cliente.post(f"/api/lotes/{lote['id']}/encerrar")
    depois = agora_utc() + timedelta(minutes=1)

    assert resposta.status_code == 200
    encerrado = resposta.json()
    assert encerrado["status"] == "encerrado"
    assert encerrado["id"] == lote["id"]
    fim = datetime.strptime(encerrado["fim"], "%Y-%m-%dT%H:%M:%SZ")
    assert antes <= fim <= depois


def test_encerrar_com_fim_informado(cliente):
    lote = criar_lote(cliente)
    resposta = cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-25T18:00:00Z"})

    assert resposta.status_code == 200
    assert resposta.json()["fim"] == "2026-10-25T18:00:00Z"
    assert resposta.json()["status"] == "encerrado"
    # o formato e o de um item de GET /api/lotes
    assert "risco" in resposta.json()
    assert "faixa_segura" in resposta.json()


def test_encerrar_com_fim_anterior_ao_inicio_devolve_400(cliente):
    lote = criar_lote(cliente)
    resposta = cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-24T08:00:00Z"})
    assert resposta.status_code == 400
    assert "erro" in resposta.json()

    # o lote continua em transito
    assert cliente.get(f"/api/lotes/{lote['id']}").json()["status"] == "em_transito"


def test_encerrar_duas_vezes_devolve_400(cliente):
    lote = criar_lote(cliente)
    primeira = cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-25T18:00:00Z"})
    assert primeira.status_code == 200

    segunda = cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-25T19:00:00Z"})
    assert segunda.status_code == 400
    assert "erro" in segunda.json()


def test_encerrar_lote_inexistente_devolve_404(cliente):
    resposta = cliente.post("/api/lotes/99/encerrar")
    assert resposta.status_code == 404
    assert "erro" in resposta.json()


# ---------- leituras do lote ----------

def test_leituras_do_lote_inexistente_devolve_404(cliente):
    resposta = cliente.get("/api/lotes/99/leituras")
    assert resposta.status_code == 404
    assert "erro" in resposta.json()


def test_leituras_do_lote_sem_leituras_devolve_lista_vazia(cliente):
    lote = criar_lote(cliente)
    resposta = cliente.get(f"/api/lotes/{lote['id']}/leituras")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_leituras_do_lote_vem_em_ordem_cronologica(cliente):
    lote = criar_lote(cliente)
    # gravadas fora de ordem de proposito
    gravar_leituras([
        (2, 1.0, 90.0, None),
        (0, 1.0, 90.0, None),
        (1, 1.0, 90.0, None),
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    horas = [l["data_hora"] for l in leituras]
    assert horas == ["2026-10-24T09:00:00Z", "2026-10-24T10:00:00Z", "2026-10-24T11:00:00Z"]


def test_leituras_do_lote_marcam_fora_da_faixa_de_temperatura(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, None),
        (1, 6.4, 90.0, None),
        (2, -0.5, 90.0, None),
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert [l["fora_faixa_temp"] for l in leituras] == [False, True, True]
    # umidade 90 esta dentro de 85-95
    assert [l["fora_faixa_umidade"] for l in leituras] == [False, False, False]


def test_leituras_do_lote_marcam_fora_da_faixa_de_umidade(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, None),
        (1, 1.0, 82.0, None),
        (2, 1.0, 97.0, None),
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert [l["fora_faixa_umidade"] for l in leituras] == [False, True, True]
    assert [l["fora_faixa_temp"] for l in leituras] == [False, False, False]


def test_leituras_do_lote_marcam_porta_aberta_acima_de_300_lux(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, 5.0),
        (1, 1.0, 90.0, 640.0),
        (2, 1.0, 90.0, 300.0),
        (3, 1.0, 90.0, 300.1),
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert [l["porta_aberta"] for l in leituras] == [False, True, False, True]


def test_leitura_com_luminosidade_nula_tem_porta_aberta_falsa(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([(0, 1.0, 90.0, None)])

    leitura = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()[0]
    assert leitura["luminosidade_lux"] is None
    assert leitura["porta_aberta"] is False


def test_leitura_tem_todos_os_campos_do_contrato(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([(0, 6.4, 82.0, 640.0)])

    leitura = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()[0]
    assert leitura == {
        "data_hora": "2026-10-24T09:00:00Z",
        "temperatura_c": 6.4,
        "umidade_pct": 82.0,
        "luminosidade_lux": 640.0,
        "fora_faixa_temp": True,
        "fora_faixa_umidade": True,
        "porta_aberta": True,
    }


def test_leituras_do_lote_usam_a_faixa_copiada_no_lote(cliente):
    faixa = {"temp_min_c": 0.0, "temp_max_c": 8.0, "umidade_min_pct": 85.0, "umidade_max_pct": 95.0}
    lote = criar_lote(cliente, faixa_segura=faixa)
    gravar_leituras([(0, 6.4, 90.0, None)])  # 6,4 esta dentro de 0-8

    leitura = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()[0]
    assert leitura["fora_faixa_temp"] is False


def test_leituras_do_lote_nao_incluem_as_de_fora_do_intervalo(cliente):
    lote = criar_lote(cliente)
    cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-24T11:00:00Z"})
    gravar_leituras([
        (-1, 1.0, 90.0, None),   # antes do inicio
        (0, 1.0, 90.0, None),
        (2, 1.0, 90.0, None),
        (3, 1.0, 90.0, None),    # depois do fim
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert len(leituras) == 2


def test_leituras_descartadas_pela_auditoria_nao_aparecem(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, None),
        (1, -41.0, 90.0, None),
        (2, 81.0, 90.0, None),
    ])

    leituras = cliente.get(f"/api/lotes/{lote['id']}/leituras").json()
    assert len(leituras) == 1


# ---------- formato das datas ----------

def test_datas_do_json_terminam_em_z(cliente):
    lote = criar_lote(cliente)
    gravar_leituras([
        (0, 1.0, 90.0, 5.0),
        (1, 1.0, 90.0, 600.0),
        (2, 1.0, 90.0, 5.0),
    ])
    cliente.post(f"/api/lotes/{lote['id']}/encerrar", json={"fim": "2026-10-24T20:00:00Z"})

    respostas = [
        cliente.get("/api/lotes").json(),
        cliente.get(f"/api/lotes/{lote['id']}").json(),
        cliente.get(f"/api/lotes/{lote['id']}/leituras").json(),
    ]
    for corpo in respostas:
        datas = achar_datas(corpo)
        assert datas, "a resposta deveria ter alguma data"
        for data in datas:
            assert data.endswith("Z"), data
            # ISO 8601 sem fracao de segundo
            datetime.strptime(data, "%Y-%m-%dT%H:%M:%SZ")


def test_datas_do_lote_criado_e_encerrado_sem_informar_horario_terminam_em_z(cliente):
    corpo = {k: v for k, v in LOTE_UVA.items() if k != "inicio"}
    criado = cliente.post("/api/lotes", json=corpo).json()
    assert criado["inicio"].endswith("Z")

    encerrado = cliente.post(f"/api/lotes/{criado['id']}/encerrar").json()
    assert encerrado["inicio"].endswith("Z")
    assert encerrado["fim"].endswith("Z")
