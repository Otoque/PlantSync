"""
Testes de caixa-preta das novidades da v0.4 da API, escritos a partir de
docs/api-contrato.md: risco nos dois lados da faixa, alerta de frio, produtor,
codigos do laudo, visao publica (QR Code) e laudo completo.

As funcoes auxiliares gerais (criar_lote, gravar_leituras, em...) ficam em
auxiliares.py; as que so servem a este arquivo ficam logo abaixo.
"""

import pytest

from auxiliares import (
    FORMATO_DATA,
    alertas_do_tipo,
    analise_do_lote,
    buscar_fruta,
    cadastrar_fruta,
    conferir_data_utc,
    corpo_de_lote,
    criar_lote,
    detalhe_do_lote,
    em,
    encerrar_lote,
    fruta_melao,
    gravar_leituras,
    leituras_do_lote,
    leituras_por_hora,
    lote_da_lista,
    nova_leitura,
    sem_campo,
)

# Depois da ultima leitura de todos os testes (a maior serie vai ate 27/10 09:00).
FIM_DO_LOTE = "2026-10-28T09:00:00Z"

MENSAGEM_NAO_ENCONTRADO = {"erro": "Código não encontrado."}

# Manga: faixa de 10 a 13 °C. Uva: faixa de 0 a 2 °C.
MANGA_ABAIXO_DO_PISO_72_HORAS = [8.5] * 73  # 72 intervalos de 1 h

# Uma leitura por hora: 72 h de frio a 8,5 °C, volta a faixa (12 °C),
# 9 h de calor a 15 °C (2 °C acima do teto = 18 °C·h) e volta a faixa de novo.
MANGA_FRIO_E_DEPOIS_CALOR = [8.5] * 73 + [12.0] + [15.0] * 9 + [12.0]


# ---------- funcoes auxiliares deste arquivo ----------

def leituras_nas_horas(temperaturas):
    """Uma leitura por hora, da hora 0 em diante, com a temperatura de cada posicao da lista."""
    leituras = []
    for hora, temperatura in enumerate(temperaturas):
        leituras.append(nova_leitura(em(hora), temperatura))
    return leituras


def criar_lote_de_manga(cliente, **mudancas):
    """Cria um lote de manga (faixa 10 a 13 °C); exige status 201."""
    return criar_lote(cliente, fruta="manga", **mudancas)


def criar_lote_encerrado_sem_buracos(cliente, banco, temperaturas, fruta="manga"):
    """
    Uma leitura a cada 10 min desde o inicio do lote, encerrando na ultima.
    Assim o selo so depende do nivel de risco, nao da falta de dados.
    """
    lote = criar_lote(cliente, fruta=fruta)
    leituras = []
    for numero, temperatura in enumerate(temperaturas):
        leituras.append(nova_leitura(em(0, numero * 10), temperatura))
    gravar_leituras(banco, leituras)
    fim = em(0, (len(temperaturas) - 1) * 10).strftime(FORMATO_DATA)
    resposta = encerrar_lote(cliente, lote, fim=fim)
    assert resposta.status_code == 200, resposta.text
    return lote


def criar_lote_encerrado(cliente, banco, temperaturas, fruta="manga"):
    """Cria o lote, grava uma leitura por hora e encerra depois da ultima leitura."""
    lote = criar_lote(cliente, fruta=fruta)
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    resposta = encerrar_lote(cliente, lote, fim=FIM_DO_LOTE)
    assert resposta.status_code == 200, resposta.text
    return lote


def visao_publica(cliente, lote):
    """Abre GET /api/publico/<codigo_publico do lote> e devolve a resposta."""
    codigo = detalhe_do_lote(cliente, lote)["codigo_publico"]
    return cliente.get(f"/api/publico/{codigo}")


def alerta_do_lado(cliente, lado):
    """Devolve o unico alerta risco_termico do 'lado' pedido; falha se nao houver um so."""
    alertas = alertas_do_tipo(cliente, "risco_termico")
    do_lado = [alerta for alerta in alertas if alerta["lado"] == lado]
    assert len(do_lado) == 1, alertas
    return do_lado[0]


# ---------- frio: graus-hora e nivel ----------

def test_manga_a_8_5_graus_por_72_horas_soma_108_graus_hora_abaixo(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas(MANGA_ABAIXO_DO_PISO_72_HORAS))
    analise = analise_do_lote(cliente, lote)
    # 1,5 °C abaixo do piso por 72 h = 108 °C·h
    assert analise["graus_hora_abaixo"] == 108
    assert analise["graus_hora_acima"] == 0
    assert analise["nivel_abaixo"] == "VERMELHO"
    assert analise["nivel_acima"] == "VERDE"
    assert analise["nivel"] == "VERMELHO"


def test_lista_de_lotes_mostra_o_risco_de_frio_da_manga(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas(MANGA_ABAIXO_DO_PISO_72_HORAS))
    risco = lote_da_lista(cliente, lote)["risco"]
    assert risco["graus_hora_abaixo"] == 108
    assert risco["graus_hora_acima"] == 0
    assert risco["nivel"] == "VERMELHO"


def test_graus_hora_unico_deixou_de_existir_no_risco_e_na_analise(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas(MANGA_ABAIXO_DO_PISO_72_HORAS))
    assert "graus_hora" not in lote_da_lista(cliente, lote)["risco"]
    assert "graus_hora" not in analise_do_lote(cliente, lote)


# parametrize roda o mesmo teste uma vez para cada valor da lista; os nomes entre
# aspas sao os parametros da funcao, na mesma ordem. Os 'ids' so dao nome a cada caso.
@pytest.mark.parametrize("temperatura", [10.0, 13.0], ids=["no_piso", "no_teto"])
def test_leitura_exatamente_no_piso_ou_no_teto_nao_soma_nada(cliente, banco, temperatura):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_por_hora(temperatura, horas=10))
    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora_abaixo"] == 0
    assert analise["graus_hora_acima"] == 0
    assert analise["nivel_abaixo"] == "VERDE"
    assert analise["nivel_acima"] == "VERDE"
    assert analise["nivel"] == "VERDE"
    assert analise["trechos_fora_faixa"] == []


def test_lote_com_frio_e_calor_soma_cada_lado_separado(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    # Frio: 1,5 × 72 h = 108, mais a volta para 12 °C (media 0,75 por 1 h) = 108,75 °C·h.
    # Calor: 12 -> 15 °C (media 1 por 1 h) + 2 × 8 h + 15 -> 12 °C (media 1 por 1 h) = 18 °C·h.
    temperaturas = MANGA_FRIO_E_DEPOIS_CALOR
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    analise = analise_do_lote(cliente, lote)
    assert analise["graus_hora_abaixo"] == 108.75
    assert analise["graus_hora_acima"] == 18
    assert analise["nivel_abaixo"] == "VERMELHO"
    assert analise["nivel_acima"] == "AMARELO"


def test_nivel_do_lote_e_o_pior_dos_dois_lados_quando_o_frio_e_o_pior(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    temperaturas = MANGA_FRIO_E_DEPOIS_CALOR
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    assert analise_do_lote(cliente, lote)["nivel"] == "VERMELHO"
    assert lote_da_lista(cliente, lote)["risco"]["nivel"] == "VERMELHO"


def test_nivel_do_lote_e_o_pior_dos_dois_lados_quando_o_calor_e_o_pior(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    # 12 h a 18 °C (5 × 12 = 60 °C·h acima), volta para 12 °C e 4 h a 8,5 °C (6 °C·h abaixo)
    temperaturas = [18.0] * 13 + [12.0] + [8.5] * 4 + [12.0]
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    analise = analise_do_lote(cliente, lote)
    assert analise["nivel_acima"] == "VERMELHO"
    assert analise["nivel_abaixo"] == "AMARELO"
    assert analise["nivel"] == "VERMELHO"


def test_um_lado_nao_compensa_o_outro_no_nivel(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    # Frio de 1,5 × 4 = 6 °C·h e calor de 3 × 4 = 12 °C·h: os dois lados sao AMARELO
    temperaturas = [8.5] * 5 + [12.0] + [16.0] * 4 + [12.0]
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    analise = analise_do_lote(cliente, lote)
    assert analise["nivel_abaixo"] == "AMARELO"
    assert analise["nivel_acima"] == "AMARELO"
    assert analise["nivel"] == "AMARELO"


def test_lote_sem_leituras_tem_os_tres_niveis_sem_dados(cliente):
    lote = criar_lote_de_manga(cliente)
    analise = analise_do_lote(cliente, lote)
    assert analise["nivel_acima"] == "SEM_DADOS"
    assert analise["nivel_abaixo"] == "SEM_DADOS"
    assert analise["nivel"] == "SEM_DADOS"
    assert analise["trechos_fora_faixa"] == []
    risco = lote_da_lista(cliente, lote)["risco"]
    assert risco["graus_hora_acima"] == 0
    assert risco["graus_hora_abaixo"] == 0


# ---------- trechos_fora_faixa ----------

def test_trecho_abaixo_do_piso_traz_lado_temperatura_extrema_e_datas_em_utc(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    # Horas 1 a 3 abaixo de 10 °C; a mais fria e 7 °C
    gravar_leituras(banco, leituras_nas_horas([12.0, 8.0, 7.0, 9.0, 12.0]))
    trechos = analise_do_lote(cliente, lote)["trechos_fora_faixa"]
    assert len(trechos) == 1
    trecho = trechos[0]
    assert trecho["lado"] == "abaixo"
    assert trecho["temp_extrema_c"] == 7.0
    assert trecho["inicio"] == "2026-10-24T10:00:00Z"
    assert trecho["fim"] == "2026-10-24T12:00:00Z"
    assert trecho["duracao_min"] == 120
    conferir_data_utc(trecho["inicio"])
    conferir_data_utc(trecho["fim"])


def test_trecho_acima_do_teto_guarda_a_maior_temperatura(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas([12.0, 14.0, 16.0, 14.5, 12.0]))
    trechos = analise_do_lote(cliente, lote)["trechos_fora_faixa"]
    assert len(trechos) == 1
    assert trechos[0]["lado"] == "acima"
    assert trechos[0]["temp_extrema_c"] == 16.0
    assert trechos[0]["duracao_min"] == 120


def test_trecho_de_uma_leitura_so_tem_duracao_zero(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas([12.0, 15.0, 12.0]))
    trechos = analise_do_lote(cliente, lote)["trechos_fora_faixa"]
    assert len(trechos) == 1
    assert trechos[0]["duracao_min"] == 0
    assert trechos[0]["inicio"] == trechos[0]["fim"] == "2026-10-24T10:00:00Z"
    assert trechos[0]["lado"] == "acima"
    assert trechos[0]["temp_extrema_c"] == 15.0


def test_frio_e_calor_em_sequencia_viram_trechos_separados_em_ordem(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    # Frio nas horas 1 e 2, calor nas horas 3 e 4 (sem voltar para a faixa entre eles)
    gravar_leituras(banco, leituras_nas_horas([12.0, 9.0, 8.0, 14.0, 15.0, 12.0]))
    trechos = analise_do_lote(cliente, lote)["trechos_fora_faixa"]
    assert [trecho["lado"] for trecho in trechos] == ["abaixo", "acima"]
    assert trechos[0]["temp_extrema_c"] == 8.0
    assert trechos[1]["temp_extrema_c"] == 15.0


def test_trechos_estao_no_detalhe_e_nao_no_resumo_da_lista(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas([12.0, 8.0, 12.0]))
    assert "trechos_fora_faixa" in detalhe_do_lote(cliente, lote)["analise"]
    assert "trechos_fora_faixa" not in lote_da_lista(cliente, lote)["risco"]


# ---------- alertas de frio ----------

def test_alerta_de_frio_da_manga_usa_a_mensagem_do_contrato(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas(MANGA_ABAIXO_DO_PISO_72_HORAS))
    alerta = alerta_do_lado(cliente, "abaixo")
    numero = lote["id"]
    assert alerta["lote_id"] == numero
    assert alerta["fruta"] == "manga"
    assert alerta["nivel"] == "VERMELHO"
    assert alerta["mensagem"] == (
        f"Lote {numero} (manga) acumulou 108 °C·h abaixo de 10 °C: risco de corte negro, "
        "redirecionar para mercado interno ou processamento."
    )
    conferir_data_utc(alerta["data_hora"])


def test_lote_so_com_frio_nao_gera_alerta_de_calor(cliente, banco):
    criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas(MANGA_ABAIXO_DO_PISO_72_HORAS))
    alertas = alertas_do_tipo(cliente, "risco_termico")
    assert [alerta["lado"] for alerta in alertas] == ["abaixo"]


def test_lote_com_calor_e_frio_gera_dois_alertas_um_por_lado(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    temperaturas = MANGA_FRIO_E_DEPOIS_CALOR
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    alertas = alertas_do_tipo(cliente, "risco_termico")
    assert len(alertas) == 2
    por_lado = {}
    for alerta in alertas:
        por_lado[alerta["lado"]] = alerta
    assert sorted(por_lado) == ["abaixo", "acima"]
    assert por_lado["abaixo"]["nivel"] == "VERMELHO"
    assert por_lado["acima"]["nivel"] == "AMARELO"
    assert por_lado["acima"]["lote_id"] == lote["id"]
    assert "acima de 13 °C" in por_lado["acima"]["mensagem"]
    assert "abaixo de 10 °C" in por_lado["abaixo"]["mensagem"]


def test_alertas_vem_do_mais_grave_para_o_mais_leve_mesmo_com_dois_lados(cliente, banco):
    criar_lote_de_manga(cliente)
    temperaturas = MANGA_FRIO_E_DEPOIS_CALOR
    gravar_leituras(banco, leituras_nas_horas(temperaturas))
    niveis = []
    for alerta in cliente.get("/api/alertas").json():
        niveis.append(alerta["nivel"])
    assert niveis == ["VERMELHO", "AMARELO"]


def test_alerta_de_frio_de_fruta_sem_risco_no_frio_nao_cita_o_dano(cliente, banco):
    lote = criar_lote(cliente, fruta="uva")
    # 2 °C abaixo do piso de 0 °C por 12 h = 24 °C·h
    gravar_leituras(banco, leituras_nas_horas([-2.0] * 13))
    alerta = alerta_do_lado(cliente, "abaixo")
    assert alerta["nivel"] == "LARANJA"
    assert "risco de" not in alerta["mensagem"]
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 24 °C·h abaixo de 0 °C: "
        "inspecionar antes do embarque."
    )


def test_alerta_de_calor_continua_com_lado_acima_e_sem_citar_dano(cliente, banco):
    lote = criar_lote(cliente, fruta="uva")
    # 2 °C acima do teto de 2 °C por 12 h = 24 °C·h
    gravar_leituras(banco, leituras_nas_horas([4.0] * 13))
    alerta = alerta_do_lado(cliente, "acima")
    assert alerta["mensagem"] == (
        f"Lote {lote['id']} (uva) acumulou 24 °C·h acima de 2 °C: "
        "inspecionar antes do embarque."
    )


def test_alerta_de_porta_aberta_tem_lado_nulo(cliente, banco):
    criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_por_hora(12.0, horas=10, horas_com_porta_aberta=[3, 4]))
    alertas = alertas_do_tipo(cliente, "porta_aberta")
    assert len(alertas) == 1
    assert "lado" in alertas[0]
    assert alertas[0]["lado"] is None


# ---------- produtor ----------

def test_cadastro_sem_produtor_devolve_400_com_mensagem_do_campo(cliente):
    resposta = cliente.post("/api/lotes", json=sem_campo(corpo_de_lote(), "produtor"))
    assert resposta.status_code == 400
    assert resposta.json()["erro"].startswith("produtor:")


def test_produtor_aparece_na_resposta_do_cadastro_na_lista_e_no_detalhe(cliente):
    lote = criar_lote(cliente, produtor="Fazenda Três Irmãos")
    assert lote["produtor"] == "Fazenda Três Irmãos"
    assert lote_da_lista(cliente, lote)["produtor"] == "Fazenda Três Irmãos"
    assert detalhe_do_lote(cliente, lote)["produtor"] == "Fazenda Três Irmãos"


# ---------- codigo_publico e token_laudo ----------

def test_codigo_publico_aparece_no_cadastro_na_lista_e_no_detalhe(cliente):
    lote = criar_lote(cliente)
    codigo = lote["codigo_publico"]
    assert isinstance(codigo, str)
    assert codigo != ""
    assert lote_da_lista(cliente, lote)["codigo_publico"] == codigo
    assert detalhe_do_lote(cliente, lote)["codigo_publico"] == codigo


def test_token_laudo_so_aparece_no_detalhe(cliente):
    lote = criar_lote(cliente)
    assert "token_laudo" not in lote
    assert "token_laudo" not in lote_da_lista(cliente, lote)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    assert isinstance(token, str)
    assert token != ""


def test_token_laudo_nao_aparece_na_resposta_do_encerramento(cliente):
    lote = criar_lote(cliente)
    encerrado = encerrar_lote(cliente, lote).json()
    assert "token_laudo" not in encerrado


def test_codigo_publico_nao_e_o_id_do_lote_nem_o_token(cliente):
    lote = criar_lote(cliente)
    detalhe = detalhe_do_lote(cliente, lote)
    assert detalhe["codigo_publico"] != str(lote["id"])
    assert detalhe["codigo_publico"] != detalhe["token_laudo"]


def test_dois_lotes_tem_codigos_e_tokens_diferentes(cliente):
    primeiro = criar_lote(cliente)
    encerrar_lote(cliente, primeiro)
    # Sem inicio vale o horario atual, depois do fim do primeiro lote.
    segundo = criar_lote(cliente, inicio=None)
    detalhe_primeiro = detalhe_do_lote(cliente, primeiro)
    detalhe_segundo = detalhe_do_lote(cliente, segundo)
    assert detalhe_primeiro["codigo_publico"] != detalhe_segundo["codigo_publico"]
    assert detalhe_primeiro["token_laudo"] != detalhe_segundo["token_laudo"]


def test_codigo_e_token_do_lote_nao_mudam_entre_consultas(cliente):
    lote = criar_lote(cliente)
    primeira = detalhe_do_lote(cliente, lote)
    segunda = detalhe_do_lote(cliente, lote)
    assert primeira["codigo_publico"] == segunda["codigo_publico"]
    assert primeira["token_laudo"] == segunda["token_laudo"]


# ---------- GET /api/publico/{codigo} ----------

def test_visao_publica_tem_exatamente_fruta_produtor_origem_e_selo(cliente, banco):
    lote = criar_lote_encerrado_sem_buracos(cliente, banco, [12.0] * 11)
    resposta = visao_publica(cliente, lote)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "fruta": "Manga",
        "produtor": "Sítio Boa Vista",
        "origem": "Packing house Petrolina",
        "selo_faixa_segura": True,
    }


def test_visao_publica_mostra_o_nome_da_fruta_e_nao_o_id(cliente):
    lote = criar_lote(cliente, fruta="uva")
    assert visao_publica(cliente, lote).json()["fruta"] == "Uva de mesa"


def test_visao_publica_nunca_traz_temperatura_nivel_leituras_nem_token(cliente, banco):
    lote = criar_lote_encerrado(cliente, banco, MANGA_ABAIXO_DO_PISO_72_HORAS)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    resposta = visao_publica(cliente, lote)
    corpo = resposta.json()
    assert sorted(corpo) == ["fruta", "origem", "produtor", "selo_faixa_segura"]
    assert token not in resposta.text
    assert "VERMELHO" not in resposta.text
    assert "graus_hora" not in resposta.text


def test_visao_publica_com_codigo_inexistente_devolve_404(cliente):
    criar_lote(cliente)
    resposta = cliente.get("/api/publico/codigo-que-nao-existe")
    assert resposta.status_code == 404
    assert resposta.json() == MENSAGEM_NAO_ENCONTRADO


def test_visao_publica_nao_abre_com_o_id_do_lote(cliente):
    lote = criar_lote(cliente)
    resposta = cliente.get(f"/api/publico/{lote['id']}")
    assert resposta.status_code == 404
    assert resposta.json() == MENSAGEM_NAO_ENCONTRADO


@pytest.mark.parametrize(
    "fruta, temperaturas",
    [
        ("manga", [12.0] * 11),
        ("uva", [1.0] * 11),
        ("manga", [8.5] * 10),  # frio marginal: 1,5 × 1,5 h = 2,25 °C·h, ainda VERDE
        ("uva", [4.0] * 10),    # calor marginal: 2 × 1,5 h = 3 °C·h, ainda VERDE
    ],
    ids=["manga_na_faixa", "uva_na_faixa", "desvio_marginal_de_frio", "desvio_marginal_de_calor"],
)
def test_selo_e_verdadeiro_quando_encerrado_com_leituras_e_verde_nos_dois_lados(
    cliente, banco, fruta, temperaturas
):
    lote = criar_lote_encerrado_sem_buracos(cliente, banco, temperaturas, fruta=fruta)
    analise = analise_do_lote(cliente, lote)
    assert analise["nivel_acima"] == "VERDE"
    assert analise["nivel_abaixo"] == "VERDE"
    assert visao_publica(cliente, lote).json()["selo_faixa_segura"] is True


def test_selo_e_falso_para_lote_em_transito_mesmo_verde(cliente, banco):
    lote = criar_lote_de_manga(cliente)
    gravar_leituras(banco, leituras_nas_horas([12.0] * 11))
    assert analise_do_lote(cliente, lote)["nivel"] == "VERDE"
    assert visao_publica(cliente, lote).json()["selo_faixa_segura"] is False


def test_selo_e_falso_para_lote_encerrado_sem_leituras(cliente, banco):
    lote = criar_lote_encerrado(cliente, banco, [])
    assert detalhe_do_lote(cliente, lote)["status"] == "encerrado"
    assert visao_publica(cliente, lote).json()["selo_faixa_segura"] is False


@pytest.mark.parametrize(
    "fruta, temperaturas, campo_do_nivel, nivel",
    [
        # Uma leitura a cada 10 min: 6 leituras a mais por hora de viagem.
        ("manga", [8.5] * 31, "nivel_abaixo", "AMARELO"),     # 1,5 × 5 h = 7,5 °C·h
        ("manga", [8.5] * 85, "nivel_abaixo", "LARANJA"),     # 1,5 × 14 h = 21 °C·h
        ("manga", [8.5] * 433, "nivel_abaixo", "VERMELHO"),   # 1,5 × 72 h = 108 °C·h
        ("uva", [4.0] * 19, "nivel_acima", "AMARELO"),        # 2 × 3 h = 6 °C·h
        ("uva", [4.0] * 73, "nivel_acima", "LARANJA"),        # 2 × 12 h = 24 °C·h
        ("uva", [4.0] * 175, "nivel_acima", "VERMELHO"),      # 2 × 29 h = 58 °C·h
    ],
    ids=[
        "frio_amarelo",
        "frio_laranja",
        "frio_vermelho",
        "calor_amarelo",
        "calor_laranja",
        "calor_vermelho",
    ],
)
def test_selo_e_falso_para_lote_encerrado_com_um_lado_amarelo_ou_pior(
    cliente, banco, fruta, temperaturas, campo_do_nivel, nivel
):
    lote = criar_lote_encerrado_sem_buracos(cliente, banco, temperaturas, fruta=fruta)
    assert analise_do_lote(cliente, lote)[campo_do_nivel] == nivel
    assert visao_publica(cliente, lote).json()["selo_faixa_segura"] is False


# ---------- GET /api/laudos/{token} ----------

def test_laudo_traz_a_analise_com_os_dois_lados_niveis_e_trechos(cliente, banco):
    lote = criar_lote_encerrado(cliente, banco, MANGA_ABAIXO_DO_PISO_72_HORAS)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    resposta = cliente.get(f"/api/laudos/{token}")
    assert resposta.status_code == 200
    laudo = resposta.json()
    assert laudo["id"] == lote["id"]
    assert laudo["fruta"] == "manga"
    assert laudo["produtor"] == "Sítio Boa Vista"
    analise = laudo["analise"]
    assert analise["graus_hora_abaixo"] == 108
    assert analise["graus_hora_acima"] == 0
    assert analise["nivel_abaixo"] == "VERMELHO"
    assert analise["nivel_acima"] == "VERDE"
    assert analise["nivel"] == "VERMELHO"
    assert len(analise["trechos_fora_faixa"]) == 1
    assert analise["trechos_fora_faixa"][0]["lado"] == "abaixo"
    assert analise["trechos_fora_faixa"][0]["temp_extrema_c"] == 8.5


def test_laudo_traz_a_curva_da_viagem_no_formato_de_leituras_do_lote(cliente, banco):
    lote = criar_lote_encerrado(cliente, banco, [12.0, 8.0, 12.0, 15.0])
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    laudo = cliente.get(f"/api/laudos/{token}").json()
    assert len(laudo["leituras"]) == 4
    assert laudo["leituras"] == leituras_do_lote(cliente, lote)
    assert laudo["leituras"][1]["temperatura_c"] == 8.0
    assert laudo["leituras"][1]["fora_faixa_temp"] is True
    assert laudo["leituras"][0]["data_hora"] == "2026-10-24T09:00:00Z"


def test_laudo_nao_traz_o_token_laudo(cliente):
    lote = criar_lote(cliente)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    resposta = cliente.get(f"/api/laudos/{token}")
    assert resposta.status_code == 200
    assert "token_laudo" not in resposta.json()
    assert token not in resposta.text


def test_laudo_e_o_detalhe_do_lote_sem_o_token_e_com_a_curva(cliente, banco):
    lote = criar_lote_encerrado(cliente, banco, [12.0, 8.0, 12.0, 15.0, 12.0])
    detalhe = detalhe_do_lote(cliente, lote)
    laudo = cliente.get(f"/api/laudos/{detalhe['token_laudo']}").json()
    del detalhe["token_laudo"]
    del laudo["leituras"]
    assert laudo == detalhe


def test_laudo_de_lote_sem_leituras_traz_curva_vazia_e_niveis_sem_dados(cliente):
    lote = criar_lote(cliente)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    laudo = cliente.get(f"/api/laudos/{token}").json()
    assert laudo["leituras"] == []
    assert laudo["analise"]["nivel"] == "SEM_DADOS"


def test_laudo_com_token_inexistente_devolve_404_com_a_mesma_mensagem_do_codigo(cliente):
    criar_lote(cliente)
    resposta = cliente.get("/api/laudos/token-que-nao-existe")
    assert resposta.status_code == 404
    assert resposta.json() == MENSAGEM_NAO_ENCONTRADO


def test_token_de_um_lote_nao_abre_como_codigo_publico(cliente):
    lote = criar_lote(cliente)
    token = detalhe_do_lote(cliente, lote)["token_laudo"]
    resposta = cliente.get(f"/api/publico/{token}")
    assert resposta.status_code == 404
    assert resposta.json() == MENSAGEM_NAO_ENCONTRADO


def test_codigo_publico_de_um_lote_nao_abre_como_token_do_laudo(cliente):
    lote = criar_lote(cliente)
    resposta = cliente.get(f"/api/laudos/{lote['codigo_publico']}")
    assert resposta.status_code == 404
    assert resposta.json() == MENSAGEM_NAO_ENCONTRADO


def test_token_de_um_lote_nao_abre_o_laudo_de_outro(cliente, banco):
    primeiro = criar_lote_encerrado(cliente, banco, [12.0, 8.0, 12.0])
    segundo = criar_lote(cliente, produtor="Outro Produtor", inicio=None)
    token_do_segundo = detalhe_do_lote(cliente, segundo)["token_laudo"]
    laudo = cliente.get(f"/api/laudos/{token_do_segundo}").json()
    assert laudo["id"] == segundo["id"]
    assert laudo["id"] != primeiro["id"]
    assert laudo["produtor"] == "Outro Produtor"


# ---------- risco_no_frio da fruta ----------

def test_lista_de_frutas_mostra_corte_negro_na_manga_e_nulo_na_uva(cliente):
    assert buscar_fruta(cliente, "manga")["risco_no_frio"] == "corte negro"
    uva = buscar_fruta(cliente, "uva")
    assert "risco_no_frio" in uva
    assert uva["risco_no_frio"] is None


def test_cadastro_de_fruta_sem_risco_no_frio_fica_nulo(cliente):
    corpo = sem_campo(fruta_melao(), "risco_no_frio")
    resposta = cliente.post("/api/frutas", json=corpo)
    assert resposta.status_code == 201
    assert resposta.json()["risco_no_frio"] is None
    assert buscar_fruta(cliente, "melao")["risco_no_frio"] is None


def test_cadastro_de_fruta_com_risco_no_frio_guarda_o_texto(cliente):
    resposta = cadastrar_fruta(cliente, risco_no_frio="escurecimento da casca")
    assert resposta.status_code == 201
    assert resposta.json()["risco_no_frio"] == "escurecimento da casca"
    assert buscar_fruta(cliente, "melao")["risco_no_frio"] == "escurecimento da casca"


def test_edicao_de_fruta_sem_risco_no_frio_deixa_nulo(cliente):
    corpo = sem_campo(sem_campo(fruta_melao(), "id"), "risco_no_frio")
    resposta = cliente.put("/api/frutas/manga", json=corpo)
    assert resposta.status_code == 200
    assert resposta.json()["risco_no_frio"] is None
    assert buscar_fruta(cliente, "manga")["risco_no_frio"] is None


def test_edicao_de_fruta_com_risco_no_frio_troca_o_texto(cliente):
    corpo = sem_campo(fruta_melao(risco_no_frio="dano pelo frio"), "id")
    resposta = cliente.put("/api/frutas/manga", json=corpo)
    assert resposta.status_code == 200
    assert buscar_fruta(cliente, "manga")["risco_no_frio"] == "dano pelo frio"
