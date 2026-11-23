"""Conversão transacional do histórico, mantendo as tabelas de origem intactas."""

import hashlib
from datetime import timedelta

from models.contas import Conta, Empresa
from models.catalogo import CatalogoFruta
from models.migracoes import RegistroMigracao
from models.operacao import (
    Ambiente,
    EventoLote,
    FonteSensor,
    LaudoOperacional,
    LeituraFonte,
    LoteOperacional,
    Permanencia,
    VinculoSensor,
)
from models.tabelas import Dispositivo, Fruta, Leitura, LeituraDispositivo, Lote
from services.datas import agora_utc

CHAVE_MIGRACAO = "legado_para_operacao_v1"


def migracao_aplicada(sessao):
    return sessao.get(RegistroMigracao, CHAVE_MIGRACAO)


def copiar_leituras(sessao, fonte, leituras):
    for leitura in leituras:
        sessao.add(LeituraFonte(
            fonte_id=fonte.id,
            entry_id=leitura.entry_id,
            data_hora=leitura.data_hora,
            recebida_em=agora_utc(),
            temperatura_c=leitura.temperatura_c,
            umidade_pct=leitura.umidade_pct,
            luminosidade_lux=leitura.luminosidade_lux,
        ))


def migrar_legado(sessao, empresa_id, conta_id, canal_padrao):
    """Prepara a conversão. O chamador confirma a transação ou a desfaz."""
    anterior = migracao_aplicada(sessao)
    if anterior is not None:
        if anterior.empresa_id != empresa_id:
            raise ValueError("O histórico já foi atribuído a outra empresa.")
        return dict(anterior.resumo)

    empresa = sessao.get(Empresa, empresa_id)
    conta = sessao.get(Conta, conta_id)
    if empresa is None or conta is None:
        raise ValueError("Empresa e conta de destino devem existir antes da migração.")
    if sessao.query(LoteOperacional).first() is not None:
        raise ValueError("O destino já possui lotes. Revise a conversão antes de continuar.")

    dispositivos = sessao.query(Dispositivo).order_by(Dispositivo.id).all()
    canais = [canal_padrao] + [dispositivo.canal for dispositivo in dispositivos]
    if len(set(canais)) != len(canais):
        raise ValueError("Há conflito entre canais legados. A migração foi interrompida.")

    lotes = sessao.query(Lote).order_by(Lote.id).all()
    for fruta in sessao.query(Fruta).order_by(Fruta.id):
        sessao.add(CatalogoFruta(
            empresa_id=empresa_id,
            fruta_id=fruta.id,
            nome=fruta.nome,
            temp_min_c=fruta.temp_min_c,
            temp_max_c=fruta.temp_max_c,
            umidade_min_pct=fruta.umidade_min_pct,
            umidade_max_pct=fruta.umidade_max_pct,
            risco_no_frio=fruta.risco_no_frio,
            fonte=fruta.fonte,
        ))
    leituras_padrao = sessao.query(Leitura).order_by(Leitura.id).all()
    leituras_placas = sessao.query(LeituraDispositivo).all()
    fontes = {}
    ambientes = {}
    origens = [(None, "Placa padrão", canal_padrao)]
    origens.extend((d.id, d.nome, d.canal) for d in dispositivos)
    nomes_usados = set()

    for dispositivo_id, nome, canal in origens:
        nome_fonte = nome
        sequencia = 1
        while nome_fonte in nomes_usados:
            nome_fonte = f"{nome} · canal {canal} ({sequencia})"
            sequencia += 1
        nomes_usados.add(nome_fonte)
        fonte = FonteSensor(
            empresa_id=empresa_id, nome=nome_fonte, tipo="thingspeak", canal=canal,
        )
        ambiente = Ambiente(
            empresa_id=empresa_id, nome=f"Ambiente legado · {nome_fonte}", tipo="compartimento",
        )
        sessao.add_all([fonte, ambiente])
        sessao.flush()
        fontes[dispositivo_id] = fonte
        ambientes[dispositivo_id] = ambiente
        medidas = leituras_padrao if dispositivo_id is None else [
            leitura for leitura in leituras_placas if leitura.dispositivo_id == dispositivo_id
        ]
        inicios = [leitura.data_hora for leitura in medidas]
        for lote in lotes:
            vinculo_id = lote.vinculo.dispositivo_id if lote.vinculo else None
            if vinculo_id == dispositivo_id:
                inicios.append(lote.inicio)
        inicio = min(inicios) if inicios else agora_utc()
        sessao.add(VinculoSensor(
            ambiente_id=ambiente.id, fonte_id=fonte.id, inicio=inicio, fim=None,
        ))
        copiar_leituras(sessao, fonte, medidas)

    for lote in lotes:
        dispositivo_id = lote.vinculo.dispositivo_id if lote.vinculo else None
        ambiente = ambientes[dispositivo_id]
        fruta = lote.fruta_id
        cadastro_fruta = sessao.get(Fruta, fruta)
        if cadastro_fruta is None:
            raise ValueError("Um lote legado referencia uma fruta ausente.")
        operacional = LoteOperacional(
            id=lote.id,
            codigo=f"PS-{lote.id:04d}",
            legado_id=lote.id,
            empresa_id=empresa_id,
            codigo_publico=lote.codigo_publico,
            fruta_id=fruta,
            fruta_nome=cadastro_fruta.nome,
            variedade="",
            cliente="",
            destino=lote.destino,
            produtor=lote.produtor,
            origem=lote.origem,
            tipo_destino=lote.tipo_destino,
            caixas=None,
            peso_kg=None,
            temp_min_c=lote.temp_min_c,
            temp_max_c=lote.temp_max_c,
            umidade_min_pct=lote.umidade_min_pct,
            umidade_max_pct=lote.umidade_max_pct,
            fase=2 if lote.fim is None else 3,
            versao=1,
            preparado_em=lote.inicio,
            carregado_em=None,
            despachado_em=lote.inicio,
            recebido_em=lote.fim,
            responsavel_empresa_id=empresa_id,
            responsavel_nome=conta.nome,
            ambiente_id=ambiente.id,
            pendente=False,
        )
        sessao.add(operacional)
        sessao.flush()
        # O contrato anterior incluía a amostra exatamente no encerramento.
        fim_associacao = lote.fim + timedelta(microseconds=1) if lote.fim else None
        sessao.add(Permanencia(
            lote_id=operacional.id,
            ambiente_id=ambiente.id,
            fase=2,
            responsavel_empresa_id=empresa_id,
            responsavel_nome=conta.nome,
            inicio=lote.inicio,
            fim=fim_associacao,
        ))
        sessao.add(EventoLote(
            lote_id=operacional.id,
            tipo="Importação do legado",
            autor_id=conta_id,
            empresa_id=empresa_id,
            autor_nome=conta.nome,
            empresa_nome=empresa.nome,
            efetivo_em=lote.inicio,
            registrado_em=agora_utc(),
            fase_anterior=None,
            fase_atual=operacional.fase,
            motivo="Conversão do histórico existente para a operação por empresa.",
            dados={"origem": "legado", "etapas_anteriores": "sem registros de fase"},
        ))
        sessao.add(LaudoOperacional(
            lote_id=operacional.id,
            token_hash=hashlib.sha256(lote.token_laudo.encode()).hexdigest(),
            criado_em=agora_utc(),
        ))

    resumo = {
        "lotes": len(lotes),
        "leituras": len(leituras_padrao) + len(leituras_placas),
        "fontes": len(fontes),
        "empresa_id": empresa_id,
    }
    sessao.add(RegistroMigracao(
        chave=CHAVE_MIGRACAO,
        empresa_id=empresa_id,
        aplicado_em=agora_utc(),
        resumo=resumo,
    ))
    sessao.flush()
    return resumo
