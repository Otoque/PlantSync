"""
Testes de caixa-preta da API (frutas, lotes e leituras), escritos a partir de
docs/api-contrato.md. Os testes so usam o que o contrato promete.

As funcoes auxiliares (criar_lote, gravar_leituras, em...) ficam em auxiliares.py.
"""

from datetime import timedelta

from auxiliares import (
    LOTE_UVA,
    agora_utc,
    analise_do_lote,
    buscar_fruta,
    cadastrar_fruta,
    conferir_data_utc,
    corpo_de_lote,
    criar_lote,
    detalhe_do_lote,
    editar_fruta,
    em,
    encerrar_lote,
    faixa_da_uva,
    fruta_melao,
    gravar_leituras,
    ler_data,
    leituras_do_lote,
    leituras_por_hora,
    nova_leitura,
    sem_campo,
)


# ---------- saude e frutas ----------

def test_saude_devolve_status_ok(cliente):
    resposta = cliente.get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_listar_frutas_traz_uva_e_manga_iniciais(cliente):
    resposta = cliente.get("/api/frutas")
    assert resposta.status_code == 200

    ids = []
    for fruta in resposta.json():
        ids.append(fruta["id"])
    assert set(ids) == {"uva", "manga"}

    uva = buscar_fruta(cliente, "uva")
    assert uva["temp_min_c"] == 0.0
    assert uva["temp_max_c"] == 2.0
    assert uva["umidade_min_pct"] == 85.0
    assert uva["umidade_max_pct"] == 95.0

    manga = buscar_fruta(cliente, "manga")
    assert manga["temp_min_c"] == 10.0
    assert manga["temp_max_c"] == 13.0
    assert manga["umidade_min_pct"] == 85.0
    assert manga["umidade_max_pct"] == 90.0


def test_cadastrar_fruta_valida_devolve_201_e_aparece_na_lista(cliente):
    resposta = cadastrar_fruta(cliente)
    assert resposta.status_code == 201
    assert resposta.json() == fruta_melao()

    ids = [fruta["id"] for fruta in cliente.get("/api/frutas").json()]
    assert "melao" in ids


def test_cadastrar_fruta_com_id_repetido_devolve_400(cliente):
    cadastrar_fruta(cliente)
    resposta = cadastrar_fruta(cliente)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_cadastrar_fruta_com_id_de_fruta_inicial_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, id="uva")
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_temp_min_igual_a_temp_max_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, temp_min_c=5.0, temp_max_c=5.0)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_cadastrar_fruta_com_temp_min_maior_que_temp_max_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, temp_min_c=8.0, temp_max_c=5.0)
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_min_maior_que_max_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, umidade_min_pct=96.0, umidade_max_pct=90.0)
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_acima_de_100_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, umidade_max_pct=101.0)
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_umidade_abaixo_de_0_devolve_400(cliente):
    resposta = cadastrar_fruta(cliente, umidade_min_pct=-1.0)
    assert resposta.status_code == 400


def test_cadastrar_fruta_com_id_invalido_devolve_400(cliente):
    # o id so aceita letras minusculas sem acento, numeros, - ou _
    for id_ruim in ["Melao", "melão", "meu melao", "melao!"]:
        resposta = cadastrar_fruta(cliente, id=id_ruim)
        assert resposta.status_code == 400, id_ruim


def test_cadastrar_fruta_aceita_id_com_hifen_underline_e_numero(cliente):
    resposta = cadastrar_fruta(cliente, id="melao-2_b")
    assert resposta.status_code == 201


def test_cadastrar_fruta_sem_campo_obrigatorio_devolve_400(cliente):
    corpo = sem_campo(fruta_melao(), "fonte")
    resposta = cliente.post("/api/frutas", json=corpo)
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_erro_de_fruta_segue_o_formato_com_chave_erro(cliente):
    resposta = cadastrar_fruta(cliente, temp_min_c=9.0, temp_max_c=5.0)
    corpo = resposta.json()
    assert list(corpo.keys()) == ["erro"]
    assert isinstance(corpo["erro"], str)
    assert corpo["erro"] != ""


def test_editar_fruta_devolve_200_com_os_novos_valores(cliente):
    resposta = editar_fruta(
        cliente, "uva", nome="Uva sem semente", temp_min_c=0.0, temp_max_c=4.0
    )
    assert resposta.status_code == 200
    assert resposta.json()["id"] == "uva"
    assert resposta.json()["nome"] == "Uva sem semente"
    assert resposta.json()["temp_max_c"] == 4.0

    assert buscar_fruta(cliente, "uva")["temp_max_c"] == 4.0


def test_editar_fruta_inexistente_devolve_404(cliente):
    resposta = editar_fruta(cliente, "abacaxi")
    assert resposta.status_code == 404
    assert "erro" in resposta.json()


def test_editar_fruta_com_faixa_invalida_devolve_400(cliente):
    resposta = editar_fruta(cliente, "uva", temp_min_c=9.0, temp_max_c=5.0)
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
    assert lote["faixa_segura"] == faixa_da_uva()
    assert lote["risco"]["nivel"] == "SEM_DADOS"
    assert lote["risco"]["graus_hora"] == 0


def test_criar_lote_sem_inicio_usa_o_horario_atual(cliente):
    corpo = sem_campo(LOTE_UVA, "inicio")
    antes = agora_utc() - timedelta(minutes=1)
    resposta = cliente.post("/api/lotes", json=corpo)
    depois = agora_utc() + timedelta(minutes=1)

    assert resposta.status_code == 201
    inicio = ler_data(resposta.json()["inicio"])
    assert antes <= inicio <= depois


def test_criar_lote_com_fruta_inexistente_devolve_400(cliente):
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(fruta="abacaxi"))
    assert resposta.status_code == 400
    assert "abacaxi" in resposta.json()["erro"]


def test_criar_lote_sem_origem_devolve_400(cliente):
    resposta = cliente.post("/api/lotes", json=sem_campo(LOTE_UVA, "origem"))
    assert resposta.status_code == 400
    assert "erro" in resposta.json()


def test_criar_lote_sem_porto_destino_devolve_400(cliente):
    resposta = cliente.post("/api/lotes", json=sem_campo(LOTE_UVA, "porto_destino"))
    assert resposta.status_code == 400


def test_segundo_lote_em_transito_devolve_400_citando_o_lote_aberto(cliente):
    primeiro = criar_lote(cliente)
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(fruta="manga"))
    assert resposta.status_code == 400
    assert f"lote {primeiro['id']}" in resposta.json()["erro"]


def test_depois_de_encerrar_o_lote_e_possivel_criar_outro(cliente):
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro)
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(fruta="manga"))
    assert resposta.status_code == 201


def test_criar_lote_com_faixa_segura_propria(cliente):
    faixa = faixa_da_uva(
        temp_min_c=1.0, temp_max_c=3.0, umidade_min_pct=80.0, umidade_max_pct=92.0
    )
    lote = criar_lote(cliente, faixa_segura=faixa)
    assert lote["faixa_segura"] == faixa

    # a fruta continua com a faixa original
    assert buscar_fruta(cliente, "uva")["temp_max_c"] == 2.0


def test_criar_lote_com_faixa_segura_propria_invalida_devolve_400(cliente):
    faixa = faixa_da_uva(temp_min_c=5.0, temp_max_c=3.0)
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(faixa_segura=faixa))
    assert resposta.status_code == 400


def test_criar_lote_com_faixa_segura_de_umidade_acima_de_100_devolve_400(cliente):
    faixa = faixa_da_uva(temp_max_c=3.0, umidade_max_pct=120.0)
    resposta = cliente.post("/api/lotes", json=corpo_de_lote(faixa_segura=faixa))
    assert resposta.status_code == 400


def test_editar_fruta_depois_nao_muda_a_faixa_do_lote_ja_criado(cliente):
    lote = criar_lote(cliente)

    resposta = editar_fruta(
        cliente, "uva", nome="Uva de mesa", temp_min_c=0.0, temp_max_c=4.0,
        umidade_min_pct=70.0, umidade_max_pct=99.0,
    )
    assert resposta.status_code == 200

    detalhe = detalhe_do_lote(cliente, lote)
    assert detalhe["faixa_segura"]["temp_max_c"] == 2.0
    assert detalhe["faixa_segura"]["umidade_min_pct"] == 85.0

    item_da_lista = cliente.get("/api/lotes").json()[0]
    assert item_da_lista["faixa_segura"]["temp_max_c"] == 2.0


def test_editar_fruta_depois_nao_muda_o_risco_do_lote_ja_criado(cliente, banco):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h
    gravar_leituras(banco, leituras_por_hora(5.0))

    editar_fruta(
        cliente, "uva", nome="Uva de mesa", temp_min_c=0.0, temp_max_c=10.0,
        umidade_min_pct=85.0, umidade_max_pct=95.0,
    )

    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora"] == 30.0
    assert analise["amostras_fora_faixa"] == 11


def test_editar_fruta_vale_para_o_lote_novo(cliente):
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro)

    editar_fruta(
        cliente, "uva", nome="Uva de mesa", temp_min_c=0.0, temp_max_c=4.0,
        umidade_min_pct=85.0, umidade_max_pct=95.0,
    )

    novo = criar_lote(cliente)
    assert novo["faixa_segura"]["temp_max_c"] == 4.0


# ---------- listar lotes ----------

def test_listar_lotes_vazio_devolve_lista_vazia(cliente):
    resposta = cliente.get("/api/lotes")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_listar_lotes_do_mais_recente_para_o_mais_antigo(cliente):
    antigo = criar_lote(cliente, inicio="2026-10-20T09:00:00Z")
    encerrar_lote(cliente, antigo, fim="2026-10-21T09:00:00Z")
    recente = criar_lote(cliente, inicio="2026-10-24T09:00:00Z")

    ids = [lote["id"] for lote in cliente.get("/api/lotes").json()]
    assert ids == [recente["id"], antigo["id"]]


def test_listar_lotes_traz_resumo_de_risco(cliente, banco):
    criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h
    gravar_leituras(banco, leituras_por_hora(5.0))

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
    analise = analise_do_lote(cliente, lote)

    assert analise["amostras"] == 0
    assert analise["amostras_fora_faixa"] == 0
    assert analise["nivel"] == "SEM_DADOS"
    assert analise["primeira_leitura"] is None
    assert analise["ultima_leitura"] is None
    assert analise["temp_min_c"] is None
    assert analise["temp_max_c"] is None
    assert analise["temp_media_c"] is None
    assert analise["eventos_porta"] == []


def test_detalhe_do_lote_calcula_graus_hora_e_nivel(cliente, banco):
    lote = criar_lote(cliente)
    # 3 °C acima do limite (2 °C) por 10 h = 30 °C·h -> LARANJA (20 a menos de 50)
    gravar_leituras(banco, leituras_por_hora(5.0))

    detalhe = detalhe_do_lote(cliente, lote)
    analise = detalhe["analise"]

    assert detalhe["id"] == lote["id"]
    assert analise["amostras"] == 11
    assert analise["graus_hora"] == 30.0
    assert analise["nivel"] == "LARANJA"
    assert analise["recomendacao"] == (
        "Abuso relevante. Inspeção física obrigatória antes do embarque."
    )
    assert analise["temp_min_c"] == 5.0
    assert analise["temp_max_c"] == 5.0
    assert analise["temp_media_c"] == 5.0
    assert analise["primeira_leitura"] == "2026-10-24T09:00:00Z"
    assert analise["ultima_leitura"] == "2026-10-24T19:00:00Z"


def test_detalhe_do_lote_nivel_verde_quando_tudo_dentro_da_faixa(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, leituras_por_hora(1.0, horas=4))

    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora"] == 0
    assert analise["nivel"] == "VERDE"
    assert analise["amostras_fora_faixa"] == 0


def test_detalhe_do_lote_nivel_vermelho_com_50_graus_hora(cliente, banco):
    lote = criar_lote(cliente)
    # 5 °C acima do limite (2 °C) por 10 h = 50 °C·h -> VERMELHO (50 ou mais)
    gravar_leituras(banco, leituras_por_hora(7.0))

    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora"] == 50.0
    assert analise["nivel"] == "VERMELHO"


def test_amostras_fora_da_faixa_contam_temperatura_acima_e_abaixo(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0),    # dentro
        nova_leitura(em(1), 5.0),    # acima de 2 °C
        nova_leitura(em(2), -1.0),   # abaixo de 0 °C
        nova_leitura(em(3), 2.0),    # no limite: ainda dentro
        nova_leitura(em(4), 0.0),    # no limite: ainda dentro
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 5
    assert analise["amostras_fora_faixa"] == 2


def test_umidade_fora_da_faixa_nao_entra_em_amostras_fora_faixa(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, umidade=50.0),   # umidade baixa, temperatura boa
        nova_leitura(em(1), 1.0, umidade=99.0),   # umidade alta, temperatura boa
        nova_leitura(em(2), 1.0, umidade=90.0),
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras_fora_faixa"] == 0


def test_detalhe_do_lote_traz_eventos_de_porta(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=5.0),
        nova_leitura(em(12), 1.0, lux=640.0),     # porta abre
        nova_leitura(em(12, 30), 1.0, lux=880.0),
        nova_leitura(em(13), 1.0, lux=700.0),     # porta ainda aberta
        nova_leitura(em(14), 1.0, lux=5.0),       # fecha
    ])

    eventos = analise_do_lote(cliente, lote)["eventos_porta"]
    assert len(eventos) == 1
    assert eventos[0]["inicio"] == "2026-10-24T21:00:00Z"
    assert eventos[0]["fim"] == "2026-10-24T22:00:00Z"
    assert eventos[0]["duracao_min"] == 60.0
    assert eventos[0]["lux_max"] == 880.0


def test_dois_eventos_de_porta_separados_viram_dois_eventos(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=500.0),
        nova_leitura(em(1), 1.0, lux=5.0),
        nova_leitura(em(2), 1.0, lux=500.0),
    ])

    eventos = analise_do_lote(cliente, lote)["eventos_porta"]
    assert len(eventos) == 2


def test_luminosidade_de_300_lux_nao_e_porta_aberta(cliente, banco):
    lote = criar_lote(cliente)
    # o contrato diz "passa de 300 lux": 300 exatos nao conta
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=300.0),
        nova_leitura(em(1), 1.0, lux=300.0),
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["eventos_porta"] == []


def test_leitura_antes_do_inicio_do_lote_nao_entra(cliente, banco):
    lote = criar_lote(cliente)  # inicio as 09:00
    gravar_leituras(banco, [
        nova_leitura(em(-2), 20.0),  # 07:00, antes do lote
        nova_leitura(em(0), 1.0),
        nova_leitura(em(1), 1.0),
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["primeira_leitura"] == "2026-10-24T09:00:00Z"
    assert analise["graus_hora"] == 0


def test_leituras_depois_do_fim_do_lote_nao_entram(cliente, banco):
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T12:00:00Z")
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0),
        nova_leitura(em(3), 1.0),    # 12:00, no fim
        nova_leitura(em(4), 30.0),   # 13:00, depois do fim
        nova_leitura(em(5), 30.0),
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["graus_hora"] == 0
    assert analise["ultima_leitura"] == "2026-10-24T12:00:00Z"


def test_lote_em_transito_recebe_tudo_o_que_chegar_depois_do_inicio(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [nova_leitura(em(0), 1.0), nova_leitura(em(100), 1.0)])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 2


def test_leitura_com_temperatura_impossivel_nao_entra_na_analise(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0),
        nova_leitura(em(1), 999.0),   # acima de 80 °C
        nova_leitura(em(2), -50.0),   # abaixo de -40 °C
        nova_leitura(em(3), 1.0),
    ])

    analise = analise_do_lote(cliente, lote)
    assert analise["amostras"] == 2
    assert analise["temp_max_c"] == 1.0
    assert analise["graus_hora"] == 0


# ---------- encerrar ----------

def test_encerrar_sem_corpo_usa_o_horario_atual(cliente):
    lote = criar_lote(cliente)
    antes = agora_utc() - timedelta(minutes=1)
    resposta = encerrar_lote(cliente, lote)
    depois = agora_utc() + timedelta(minutes=1)

    assert resposta.status_code == 200
    encerrado = resposta.json()
    assert encerrado["status"] == "encerrado"
    assert encerrado["id"] == lote["id"]
    fim = ler_data(encerrado["fim"])
    assert antes <= fim <= depois


def test_encerrar_com_fim_informado(cliente):
    lote = criar_lote(cliente)
    resposta = encerrar_lote(cliente, lote, fim="2026-10-25T18:00:00Z")

    assert resposta.status_code == 200
    assert resposta.json()["fim"] == "2026-10-25T18:00:00Z"
    assert resposta.json()["status"] == "encerrado"
    # o formato e o de um item de GET /api/lotes
    assert "risco" in resposta.json()
    assert "faixa_segura" in resposta.json()


def test_encerrar_com_fim_anterior_ao_inicio_devolve_400(cliente):
    lote = criar_lote(cliente)
    resposta = encerrar_lote(cliente, lote, fim="2026-10-24T08:00:00Z")
    assert resposta.status_code == 400
    assert "erro" in resposta.json()

    # o lote continua em transito
    assert detalhe_do_lote(cliente, lote)["status"] == "em_transito"


def test_encerrar_duas_vezes_devolve_400(cliente):
    lote = criar_lote(cliente)
    primeira = encerrar_lote(cliente, lote, fim="2026-10-25T18:00:00Z")
    assert primeira.status_code == 200

    segunda = encerrar_lote(cliente, lote, fim="2026-10-25T19:00:00Z")
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


def test_leituras_do_lote_vem_em_ordem_cronologica(cliente, banco):
    lote = criar_lote(cliente)
    # gravadas fora de ordem de proposito
    gravar_leituras(banco, [
        nova_leitura(em(2), 1.0),
        nova_leitura(em(0), 1.0),
        nova_leitura(em(1), 1.0),
    ])

    datas = []
    for leitura in leituras_do_lote(cliente, lote):
        datas.append(leitura["data_hora"])
    assert datas == ["2026-10-24T09:00:00Z", "2026-10-24T10:00:00Z", "2026-10-24T11:00:00Z"]


def test_leituras_do_lote_marcam_fora_da_faixa_de_temperatura(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0),
        nova_leitura(em(1), 6.4),
        nova_leitura(em(2), -0.5),
    ])

    temp_fora = []
    umidade_fora = []
    for leitura in leituras_do_lote(cliente, lote):
        temp_fora.append(leitura["fora_faixa_temp"])
        umidade_fora.append(leitura["fora_faixa_umidade"])
    assert temp_fora == [False, True, True]
    # umidade 90 esta dentro de 85-95
    assert umidade_fora == [False, False, False]


def test_leituras_do_lote_marcam_fora_da_faixa_de_umidade(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, umidade=90.0),
        nova_leitura(em(1), 1.0, umidade=82.0),
        nova_leitura(em(2), 1.0, umidade=97.0),
    ])

    temp_fora = []
    umidade_fora = []
    for leitura in leituras_do_lote(cliente, lote):
        temp_fora.append(leitura["fora_faixa_temp"])
        umidade_fora.append(leitura["fora_faixa_umidade"])
    assert umidade_fora == [False, True, True]
    assert temp_fora == [False, False, False]


def test_leituras_do_lote_marcam_porta_aberta_acima_de_300_lux(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=5.0),
        nova_leitura(em(1), 1.0, lux=640.0),
        nova_leitura(em(2), 1.0, lux=300.0),
        nova_leitura(em(3), 1.0, lux=300.1),
    ])

    porta_aberta = []
    for leitura in leituras_do_lote(cliente, lote):
        porta_aberta.append(leitura["porta_aberta"])
    assert porta_aberta == [False, True, False, True]


def test_leitura_com_luminosidade_nula_tem_porta_aberta_falsa(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [nova_leitura(em(0), 1.0, lux=None)])

    leitura = leituras_do_lote(cliente, lote)[0]
    assert leitura["luminosidade_lux"] is None
    assert leitura["porta_aberta"] is False


def test_leitura_tem_todos_os_campos_do_contrato(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [nova_leitura(em(0), 6.4, umidade=82.0, lux=640.0)])

    leitura = leituras_do_lote(cliente, lote)[0]
    assert leitura == {
        "data_hora": "2026-10-24T09:00:00Z",
        "temperatura_c": 6.4,
        "umidade_pct": 82.0,
        "luminosidade_lux": 640.0,
        "fora_faixa_temp": True,
        "fora_faixa_umidade": True,
        "porta_aberta": True,
    }


def test_leituras_do_lote_usam_a_faixa_copiada_no_lote(cliente, banco):
    lote = criar_lote(cliente, faixa_segura=faixa_da_uva(temp_max_c=8.0))
    gravar_leituras(banco, [nova_leitura(em(0), 6.4)])  # 6,4 esta dentro de 0-8

    leitura = leituras_do_lote(cliente, lote)[0]
    assert leitura["fora_faixa_temp"] is False


def test_leituras_do_lote_nao_incluem_as_de_fora_do_intervalo(cliente, banco):
    lote = criar_lote(cliente)
    encerrar_lote(cliente, lote, fim="2026-10-24T11:00:00Z")
    gravar_leituras(banco, [
        nova_leitura(em(-1), 1.0),   # antes do inicio
        nova_leitura(em(0), 1.0),
        nova_leitura(em(2), 1.0),
        nova_leitura(em(3), 1.0),    # depois do fim
    ])

    assert len(leituras_do_lote(cliente, lote)) == 2


def test_leituras_descartadas_pela_auditoria_nao_aparecem(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0),
        nova_leitura(em(1), -41.0),
        nova_leitura(em(2), 81.0),
    ])

    assert len(leituras_do_lote(cliente, lote)) == 1


# ---------- formato das datas ----------

def test_datas_do_json_terminam_em_z(cliente, banco):
    lote = criar_lote(cliente)
    gravar_leituras(banco, [
        nova_leitura(em(0), 1.0, lux=5.0),
        nova_leitura(em(1), 1.0, lux=600.0),
        nova_leitura(em(2), 1.0, lux=5.0),
    ])
    encerrar_lote(cliente, lote, fim="2026-10-24T20:00:00Z")

    # GET /api/lotes
    item_da_lista = cliente.get("/api/lotes").json()[0]
    conferir_data_utc(item_da_lista["inicio"])
    conferir_data_utc(item_da_lista["fim"])

    # GET /api/lotes/<id>
    detalhe = detalhe_do_lote(cliente, lote)
    analise = detalhe["analise"]
    assert len(analise["eventos_porta"]) == 1
    evento = analise["eventos_porta"][0]
    conferir_data_utc(detalhe["inicio"])
    conferir_data_utc(detalhe["fim"])
    conferir_data_utc(analise["primeira_leitura"])
    conferir_data_utc(analise["ultima_leitura"])
    conferir_data_utc(evento["inicio"])
    conferir_data_utc(evento["fim"])

    # GET /api/lotes/<id>/leituras
    leituras = leituras_do_lote(cliente, lote)
    assert len(leituras) == 3
    for leitura in leituras:
        conferir_data_utc(leitura["data_hora"])


def test_datas_do_lote_criado_e_encerrado_sem_informar_horario_terminam_em_z(cliente):
    criado = cliente.post("/api/lotes", json=sem_campo(LOTE_UVA, "inicio")).json()
    assert criado["inicio"].endswith("Z")

    encerrado = encerrar_lote(cliente, criado).json()
    assert encerrado["inicio"].endswith("Z")
    assert encerrado["fim"].endswith("Z")
