"""Regras dos lotes: cadastro, encerramento, leituras, analise e formato de resposta."""

import secrets

from models.tabelas import Fruta, Leitura, Lote
from services.analise import analisar_lote, fora_da_faixa, limpar_leituras, porta_aberta
from services.datas import agora_utc, formatar_utc, para_utc
from services.erros import ErroDeRegra, ErroNaoEncontrado
from services.frutas import validar_faixa

# Tipos de destino aceitos no cadastro do lote.
# Se mudar esta lista, mude tambem a mensagem de validar_tipo_destino.
TIPOS_DE_DESTINO = ["porto", "mercado_interno"]


def buscar_lote(sessao, lote_id):
    lote = sessao.get(Lote, lote_id)
    if lote is None:
        raise ErroNaoEncontrado(f"Lote {lote_id} não encontrado.")
    return lote


def todos_os_lotes(sessao):
    """Todos os lotes, do mais recente para o mais antigo."""
    return sessao.query(Lote).order_by(Lote.inicio.desc()).all()


def lote_em_transito(sessao):
    """Devolve o lote que ainda nao foi encerrado, ou None."""
    return sessao.query(Lote).filter(Lote.fim.is_(None)).first()


def fruta_escolhida(sessao, fruta_id):
    """
    Busca a fruta escolhida no cadastro do lote; se nao existir, diz quais existem.
    Da 400 (e nao 404, como buscar_fruta) porque o id veio no corpo do cadastro.
    """
    fruta = sessao.get(Fruta, fruta_id)
    if fruta is None:
        ids = []
        for fruta_cadastrada in sessao.query(Fruta).order_by(Fruta.id).all():
            ids.append(fruta_cadastrada.id)
        raise ErroDeRegra(f"Fruta '{fruta_id}' não cadastrada. Use: {', '.join(ids)}.")
    return fruta


def escolher_faixa(fruta, faixa_propria):
    """
    Faixa que o lote vai copiar: a propria, se veio no cadastro, ou a da fruta.
    A faixa propria (FaixaSegura) e a tabela Fruta tem os mesmos 4 campos.
    """
    if faixa_propria is None:
        return fruta
    validar_faixa(faixa_propria)
    return faixa_propria


def inicio_do_lote(dados):
    """Horario de inicio informado no cadastro, ou o horario atual."""
    if dados.inicio is None:
        return agora_utc()
    return para_utc(dados.inicio)


def gerar_codigo_publico():
    """Codigo curto e aleatorio que vai no QR Code (8 caracteres)."""
    # O modulo secrets gera texto aleatorio proprio para senhas e links secretos:
    # nao da para adivinhar o codigo de um lote a partir do codigo de outro.
    return secrets.token_urlsafe(6)


def gerar_token_laudo():
    """Segredo longo e aleatorio que abre o laudo completo (22 caracteres)."""
    return secrets.token_urlsafe(16)


def garantir_que_nao_ha_lote_em_transito(sessao):
    """Existe um so sensor (um canal), entao so um lote viaja por vez."""
    atual = lote_em_transito(sessao)
    if atual is not None:
        raise ErroDeRegra(
            f"O lote {atual.id} ainda está em trânsito. Encerre-o antes de cadastrar outro."
        )


def validar_tipo_destino(tipo_destino):
    """Levanta ErroDeRegra se o tipo nao for um dos TIPOS_DE_DESTINO."""
    if tipo_destino not in TIPOS_DE_DESTINO:
        raise ErroDeRegra("tipo_destino precisa ser 'porto' ou 'mercado_interno'.")


def criar_lote(sessao, dados):
    """
    Cadastra um lote. O lote guarda uma copia da faixa segura, para que
    editar a fruta depois nao mude a analise dele.
    """
    fruta = fruta_escolhida(sessao, dados.fruta)
    validar_tipo_destino(dados.tipo_destino)
    garantir_que_nao_ha_lote_em_transito(sessao)

    faixa = escolher_faixa(fruta, dados.faixa_segura)
    lote = Lote(
        fruta_id=fruta.id,
        produtor=dados.produtor,
        origem=dados.origem,
        destino=dados.destino,
        tipo_destino=dados.tipo_destino,
        inicio=inicio_do_lote(dados),
        fim=None,
        codigo_publico=gerar_codigo_publico(),
        token_laudo=gerar_token_laudo(),
        temp_min_c=faixa.temp_min_c,
        temp_max_c=faixa.temp_max_c,
        umidade_min_pct=faixa.umidade_min_pct,
        umidade_max_pct=faixa.umidade_max_pct,
    )
    sessao.add(lote)
    sessao.commit()
    return lote


def registrar_fim_do_lote(sessao, lote, fim):
    """Marca a chegada do lote. Sem fim informado, vale o horario atual."""
    if lote.fim is not None:
        raise ErroDeRegra(f"O lote {lote.id} já foi encerrado.")

    if fim is None:
        fim = agora_utc()
    else:
        fim = para_utc(fim)
    if fim < lote.inicio:
        raise ErroDeRegra("O fim não pode ser anterior ao início do lote.")

    lote.fim = fim
    sessao.commit()
    return lote


def faixa_do_lote(lote):
    return {
        "temp_min_c": lote.temp_min_c,
        "temp_max_c": lote.temp_max_c,
        "umidade_min_pct": lote.umidade_min_pct,
        "umidade_max_pct": lote.umidade_max_pct,
    }


def leituras_do_lote(sessao, lote):
    """
    Leituras gravadas no horario do lote, como dicionarios, sem limpeza.
    Uma leitura pertence ao lote quando o horario dela esta entre o
    inicio e o fim do lote. Lote sem fim recebe tudo depois do inicio.
    """
    consulta = sessao.query(Leitura).filter(Leitura.data_hora >= lote.inicio)
    if lote.fim is not None:
        consulta = consulta.filter(Leitura.data_hora <= lote.fim)

    lista = []
    for leitura in consulta.all():
        lista.append({
            "data_hora": leitura.data_hora,
            "temperatura_c": leitura.temperatura_c,
            "umidade_pct": leitura.umidade_pct,
            "luminosidade_lux": leitura.luminosidade_lux,
        })
    return lista


def buscar_e_analisar(sessao, lote):
    """Busca as leituras do lote no banco e calcula a analise da viagem."""
    return analisar_lote(leituras_do_lote(sessao, lote), faixa_do_lote(lote))


def leituras_para_grafico(sessao, lote):
    """Leituras limpas e em ordem, com as marcacoes que o grafico do painel usa."""
    faixa = faixa_do_lote(lote)
    resposta = []
    for leitura in limpar_leituras(leituras_do_lote(sessao, lote)):
        resposta.append(leitura_para_json(leitura, faixa))
    return resposta


def lote_basico_json(lote):
    """Campos do lote que aparecem em todas as respostas."""
    if lote.fim is None:
        status = "em_transito"
    else:
        status = "encerrado"

    return {
        "id": lote.id,
        "fruta": lote.fruta_id,
        "produtor": lote.produtor,
        "origem": lote.origem,
        "destino": lote.destino,
        "tipo_destino": lote.tipo_destino,
        "inicio": formatar_utc(lote.inicio),
        "fim": formatar_utc(lote.fim),
        "status": status,
        "codigo_publico": lote.codigo_publico,
        "faixa_segura": faixa_do_lote(lote),
    }


def lote_para_json(lote, analise):
    """Formato curto, usado na lista de lotes: o lote e o resumo do risco."""
    resposta = lote_basico_json(lote)
    resposta["risco"] = {
        "nivel": analise["nivel"],
        "graus_hora_acima": analise["graus_hora_acima"],
        "graus_hora_abaixo": analise["graus_hora_abaixo"],
    }
    return resposta


def lote_resumo_json(sessao, lote):
    """Busca a analise do lote e devolve o formato curto (lote + risco)."""
    return lote_para_json(lote, buscar_e_analisar(sessao, lote))


def intervalos_para_json(intervalos):
    """Copia cada trecho ou evento trocando inicio e fim por texto (formato do contrato)."""
    resposta = []
    for intervalo in intervalos:
        copia = dict(intervalo)
        copia["inicio"] = formatar_utc(intervalo["inicio"])
        copia["fim"] = formatar_utc(intervalo["fim"])
        resposta.append(copia)
    return resposta


def analise_para_json(analise):
    """Copia a analise trocando as datas por texto (formato do contrato)."""
    resposta = dict(analise)
    resposta["primeira_leitura"] = formatar_utc(analise["primeira_leitura"])
    resposta["ultima_leitura"] = formatar_utc(analise["ultima_leitura"])
    resposta["trechos_fora_faixa"] = intervalos_para_json(analise["trechos_fora_faixa"])
    resposta["eventos_porta"] = intervalos_para_json(analise["eventos_porta"])
    return resposta


def lote_detalhado_json(lote, analise):
    """
    Formato completo, so para o painel interno: o lote, o token do laudo
    e toda a analise da viagem.
    """
    resposta = lote_basico_json(lote)
    resposta["token_laudo"] = lote.token_laudo
    resposta["analise"] = analise_para_json(analise)
    return resposta


def leitura_para_json(leitura, faixa):
    temperatura_fora = fora_da_faixa(
        leitura["temperatura_c"], faixa["temp_min_c"], faixa["temp_max_c"]
    )
    umidade_fora = fora_da_faixa(
        leitura["umidade_pct"], faixa["umidade_min_pct"], faixa["umidade_max_pct"]
    )
    return {
        "data_hora": formatar_utc(leitura["data_hora"]),
        "temperatura_c": leitura["temperatura_c"],
        "umidade_pct": leitura["umidade_pct"],
        "luminosidade_lux": leitura["luminosidade_lux"],
        "fora_faixa_temp": temperatura_fora,
        "fora_faixa_umidade": umidade_fora,
        "porta_aberta": porta_aberta(leitura["luminosidade_lux"]),
    }
