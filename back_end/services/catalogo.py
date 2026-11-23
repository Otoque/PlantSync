"""O catálogo da empresa pode especializar as referências iniciais."""

from secrets import token_hex
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from models.catalogo import CatalogoFruta
from models.tabelas import Fruta
from services import acessos
from services.frutas import FRUTAS_INICIAIS, validar_faixa

CAMPOS = ("nome", "temp_min_c", "temp_max_c", "umidade_min_pct", "umidade_max_pct", "risco_no_frio", "fonte")


def garantir_identidades_padrao(sessao):
    for dados in FRUTAS_INICIAIS:
        if sessao.get(Fruta, dados["id"]) is None:
            sessao.add(Fruta(**dados))
    sessao.flush()


def fruta_disponivel(sessao, empresa_id, fruta_id):
    propria = sessao.get(CatalogoFruta, (empresa_id, fruta_id))
    if propria is not None:
        if not propria.ativo:
            raise HTTPException(404, "Fruta desativada neste catálogo.")
        return propria
    for dados in FRUTAS_INICIAIS:
        if dados["id"] == fruta_id and sessao.get(Fruta, fruta_id) is not None:
            return SimpleNamespace(**dados, ativo=True, versao=0)
    raise HTTPException(404, "Fruta indisponível neste catálogo.")


def fruta_json(fruta):
    return {"id": fruta.id, **{campo: getattr(fruta, campo) for campo in CAMPOS},
            "ativo": fruta.ativo, "version": fruta.versao}


def listar_frutas(sessao, empresa_id):
    registros = {fruta.fruta_id: fruta for fruta in sessao.scalars(
        select(CatalogoFruta).where(CatalogoFruta.empresa_id == empresa_id),
    )}
    for dados in FRUTAS_INICIAIS:
        fruta_id = dados["id"]
        if fruta_id not in registros and sessao.get(Fruta, fruta_id) is not None:
            registros[fruta_id] = SimpleNamespace(**dados, ativo=True, versao=0)
    return [fruta_json(fruta) for fruta in sorted(registros.values(), key=lambda item: item.nome)]


def autorizar_catalogo(sessao, contexto):
    acessos.exigir(contexto, "operar")
    if contexto.integracao:
        raise HTTPException(403, "A gestão do catálogo exige uma conta individual.")
    acessos.bloquear_empresa(sessao, contexto.empresa.id)


def criar_fruta(sessao, contexto, dados):
    autorizar_catalogo(sessao, contexto)
    fruta_id = "f-" + token_hex(12)
    identidade = Fruta(id=fruta_id, **dados)
    validar_faixa(identidade)
    sessao.add(identidade)
    sessao.flush()
    fruta = CatalogoFruta(empresa_id=contexto.empresa.id, fruta_id=fruta_id, **dados)
    sessao.add(fruta)
    sessao.flush()
    acessos.registrar_evento(sessao, contexto.empresa.id, contexto.conta.id,
                             "cadastrar_fruta", fruta=fruta_json(fruta))
    sessao.commit()
    return fruta_json(fruta)


def alterar_fruta(sessao, contexto, fruta_id, dados):
    autorizar_catalogo(sessao, contexto)
    atual = fruta_disponivel(sessao, contexto.empresa.id, fruta_id)
    versao = dados.pop("version", None)
    if versao is None or versao != atual.versao:
        raise HTTPException(409, "O catálogo mudou. Recarregue a fruta antes de editar.")
    anterior = fruta_json(atual)
    valores = {campo: getattr(atual, campo) for campo in CAMPOS}
    valores.update({campo: valor for campo, valor in dados.items() if campo in CAMPOS})
    validar_faixa(SimpleNamespace(**valores))
    if isinstance(atual, CatalogoFruta):
        fruta = atual
        for campo, valor in valores.items():
            setattr(fruta, campo, valor)
        fruta.versao += 1
    else:
        fruta = CatalogoFruta(empresa_id=contexto.empresa.id, fruta_id=fruta_id, **valores)
        sessao.add(fruta)
    sessao.flush()
    acessos.registrar_evento(sessao, contexto.empresa.id, contexto.conta.id,
                             "alterar_fruta", anterior=anterior, atual=fruta_json(fruta))
    sessao.commit()
    return fruta_json(fruta)
