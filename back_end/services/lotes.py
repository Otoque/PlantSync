"""Regras dos lotes: cadastro, encerramento, leituras, analise e formato de resposta."""

from models.tabelas import Fruta, Leitura, Lote
from services.analise import analisar_lote, fora_da_faixa, limpar_leituras, porta_aberta
from services.datas import agora_utc, formatar_utc, para_utc
from services.erros import ErroDeRegra, ErroNaoEncontrado
from services.frutas import validar_faixa


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


def criar_lote(sessao, dados):
    """
    Cadastra um lote. O lote guarda uma copia da faixa segura, para que
    editar a fruta depois nao mude a analise dele.
    """
    fruta = fruta_escolhida(sessao, dados.fruta)

    # Existe um so sensor (um canal), entao so um lote viaja por vez.
    atual = lote_em_transito(sessao)
    if atual is not None:
        raise ErroDeRegra(
            f"O lote {atual.id} ainda está em trânsito. Encerre-o antes de cadastrar outro."
        )

    faixa = escolher_faixa(fruta, dados.faixa_segura)
    lote = Lote(
        fruta_id=fruta.id,
        origem=dados.origem,
        porto_destino=dados.porto_destino,
        inicio=inicio_do_lote(dados),
        fim=None,
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
        "origem": lote.origem,
        "porto_destino": lote.porto_destino,
        "inicio": formatar_utc(lote.inicio),
        "fim": formatar_utc(lote.fim),
        "status": status,
        "faixa_segura": faixa_do_lote(lote),
    }


def lote_para_json(lote, analise):
    """Formato curto, usado na lista de lotes: o lote e o resumo do risco."""
    resposta = lote_basico_json(lote)
    resposta["risco"] = {
        "nivel": analise["nivel"],
        "graus_hora": analise["graus_hora"],
    }
    return resposta


def lote_resumo_json(sessao, lote):
    """Busca a analise do lote e devolve o formato curto (lote + risco)."""
    return lote_para_json(lote, buscar_e_analisar(sessao, lote))


def lote_detalhado_json(lote, analise):
    """Formato completo: o lote com toda a analise da viagem."""
    eventos = []
    for evento in analise["eventos_porta"]:
        eventos.append({
            "inicio": formatar_utc(evento["inicio"]),
            "fim": formatar_utc(evento["fim"]),
            "duracao_min": evento["duracao_min"],
            "lux_max": evento["lux_max"],
        })

    resposta = lote_basico_json(lote)
    resposta["analise"] = {
        "amostras": analise["amostras"],
        "amostras_fora_faixa": analise["amostras_fora_faixa"],
        "primeira_leitura": formatar_utc(analise["primeira_leitura"]),
        "ultima_leitura": formatar_utc(analise["ultima_leitura"]),
        "temp_min_c": analise["temp_min_c"],
        "temp_max_c": analise["temp_max_c"],
        "temp_media_c": analise["temp_media_c"],
        "graus_hora": analise["graus_hora"],
        "nivel": analise["nivel"],
        "recomendacao": analise["recomendacao"],
        "eventos_porta": eventos,
    }
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
