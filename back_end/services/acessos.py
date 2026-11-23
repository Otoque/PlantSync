"""Sessões, autorização por empresa e gestão de acessos da API versionada."""

import re
import secrets
from dataclasses import dataclass
from datetime import timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as insert_postgresql
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.banco import abrir_sessao
from models.contas import (
    Conta,
    ContaInicial,
    ConviteConta,
    Empresa,
    EventoAcesso,
    Integracao,
    PermissoesPapel,
    SessaoConta,
    TentativaLogin,
    VinculoConta,
)
from services import autenticacao
from services.datas import agora_utc, formatar_utc, para_utc


ADMINISTRADOR = "administrador"
PAPEIS = {
    ADMINISTRADOR: frozenset(("consultar", "operar", "compartilhar", "receber", "etiquetas", "administrar", "integrar")),
    "gestor": frozenset(("consultar", "operar", "compartilhar", "receber", "etiquetas")),
    "cliente": frozenset(("consultar",)),
}
VALIDADE_CONVITE = timedelta(days=2)
VALIDADE_MAXIMA_INTEGRACAO = timedelta(days=365)
JANELA_LOGIN_SEGUNDOS = 15 * 60
LIMITE_LOGIN_ORIGEM = 30
LIMITE_LOGIN_USUARIO = 10
PREFIXO_SESSAO = "pss_"
PREFIXO_CONVITE = "psc_"
PREFIXO_INTEGRACAO = "psi_"
esquema_bearer = HTTPBearer(auto_error=False, scheme_name="Sessão ou integração PlantSync")


@dataclass(frozen=True)
class Contexto:
    conta: Conta | None
    empresa: Empresa
    papel: str
    permissoes: frozenset[str]
    integracao: Integracao | None = None


def erro_autenticacao(mensagem=autenticacao.MENSAGEM_SEM_LOGIN):
    return HTTPException(401, mensagem, headers={"WWW-Authenticate": "Bearer"})


def exigir(contexto: Contexto, permissao: str):
    if permissao not in contexto.permissoes:
        raise HTTPException(403, "Seu vínculo não permite esta ação.")


def usuario_json(conta):
    return {"id": conta.id, "nome": conta.nome, "plataforma": conta.plataforma}


def empresa_json(empresa):
    return {"id": empresa.id, "nome": empresa.nome, "ativo": empresa.ativo}


def vinculo_json(empresa, papel, permissoes):
    return {"id": empresa.id, "nome": empresa.nome, "papel": papel, "permissoes": sorted(permissoes)}


def permissoes_do_papel(sessao, empresa_id, papel):
    limite = PAPEIS[papel]
    if papel == ADMINISTRADOR:
        return limite
    registro = sessao.get(PermissoesPapel, (empresa_id, papel))
    return limite.intersection(registro.permissoes) if registro else limite


def vinculos_ativos(sessao, conta_id):
    return sessao.execute(
        select(Empresa, VinculoConta)
        .join(VinculoConta, VinculoConta.empresa_id == Empresa.id)
        .where(VinculoConta.conta_id == conta_id, VinculoConta.ativo.is_(True), Empresa.ativo.is_(True))
        .order_by(Empresa.id)
    ).all()


def sessao_autenticada(sessao, credenciais):
    if credenciais is None or not credenciais.credentials.startswith(PREFIXO_SESSAO):
        raise erro_autenticacao()
    sessao_conta = sessao.get(SessaoConta, autenticacao.hash_do_token(credenciais.credentials), populate_existing=True)
    if sessao_conta is None or sessao_conta.expira_em <= agora_utc():
        raise erro_autenticacao()
    conta = sessao.get(Conta, sessao_conta.conta_id, populate_existing=True)
    if conta is None or not conta.ativo:
        raise erro_autenticacao()
    return sessao_conta, conta


def obter_sessao_autenticada(credenciais=Depends(esquema_bearer), sessao: Session = Depends(abrir_sessao)):
    return sessao_autenticada(sessao, credenciais)


def obter_conta(identidade=Depends(obter_sessao_autenticada)):
    return identidade[1]


def exigir_plataforma(conta: Conta = Depends(obter_conta)):
    if not conta.plataforma:
        raise HTTPException(403, "A gestão de empresas é restrita à administração da plataforma.")
    return conta


def id_empresa_solicitada(request):
    cabecalhos = request.headers.getlist("X-Empresa-ID")
    if not cabecalhos:
        return None
    if len(cabecalhos) != 1 or not re.fullmatch(r"[1-9][0-9]{0,18}", cabecalhos[0]):
        raise HTTPException(400, "Informe um X-Empresa-ID válido.")
    empresa_id = int(cabecalhos[0])
    if empresa_id > 2**63 - 1:
        raise HTTPException(400, "Informe um X-Empresa-ID válido.")
    return empresa_id


def obter_contexto(request: Request, credenciais=Depends(esquema_bearer), sessao: Session = Depends(abrir_sessao)):
    if credenciais is not None and credenciais.credentials.startswith(PREFIXO_INTEGRACAO):
        return contexto_integracao(request, sessao, credenciais.credentials)

    conta = sessao_autenticada(sessao, credenciais)[1]
    empresa_id = id_empresa_solicitada(request)
    vinculos = vinculos_ativos(sessao, conta.id)
    if empresa_id is None and len(vinculos) == 1:
        empresa, _ = vinculos[0]
        empresa_id = empresa.id
    if empresa_id is None and vinculos:
        raise HTTPException(403, "Selecione uma empresa com X-Empresa-ID.")
    for empresa, vinculo in vinculos:
        if empresa.id == empresa_id:
            permissoes = permissoes_do_papel(sessao, empresa.id, vinculo.papel)
            return Contexto(conta, empresa, vinculo.papel, permissoes)
    raise HTTPException(403, "Sua conta não tem vínculo ativo com a empresa solicitada.")


def contexto_integracao(request, sessao, token):
    integracao = sessao.scalar(select(Integracao).where(Integracao.token_hash == autenticacao.hash_do_token(token)))
    agora = agora_utc()
    if integracao is None or integracao.revogado_em is not None or integracao.expira_em <= agora:
        raise erro_autenticacao()
    request.state.integracao_auditavel = (integracao.id, integracao.empresa_id)
    empresa = sessao.get(Empresa, integracao.empresa_id)
    empresa_id = id_empresa_solicitada(request)
    if empresa is None or not empresa.ativo or empresa_id not in (None, empresa.id):
        raise HTTPException(403, "A credencial não permite acesso à empresa solicitada.")
    integracao.ultimo_uso_em = agora
    sessao.commit()
    return Contexto(None, empresa, "integracao", frozenset(integracao.permissoes), integracao)


def quantidade_tentativas(sessao, chave, janela, limite):
    inserir = {"sqlite": insert_sqlite, "postgresql": insert_postgresql}[sessao.bind.dialect.name]
    comando = inserir(TentativaLogin).values(chave=autenticacao.hash_do_token(chave), janela=janela, quantidade=1)
    comando = comando.on_conflict_do_update(
        index_elements=[TentativaLogin.chave, TentativaLogin.janela],
        set_={"quantidade": TentativaLogin.quantidade + 1},
        where=TentativaLogin.quantidade < limite,
    )
    return sessao.scalar(comando.returning(TentativaLogin.quantidade))


def reservar_tentativa_login(sessao, origem, usuario):
    instante = agora_utc().replace(tzinfo=timezone.utc).timestamp()
    janela = int(instante // JANELA_LOGIN_SEGUNDOS)
    sessao.execute(delete(TentativaLogin).where(TentativaLogin.janela < janela))
    permitido = quantidade_tentativas(sessao, f"origem:{origem}", janela, LIMITE_LOGIN_ORIGEM)
    if permitido:
        permitido = quantidade_tentativas(sessao, f"usuario:{usuario.casefold()}", janela, LIMITE_LOGIN_USUARIO)
    sessao.commit()
    if not permitido:
        espera = JANELA_LOGIN_SEGUNDOS - int(instante) % JANELA_LOGIN_SEGUNDOS
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.", headers={"Retry-After": str(espera)})


def bloquear_conta(sessao, conta_id):
    # Uma escrita mantém o bloqueio até a conclusão da transação no SQLite e no PostgreSQL.
    sessao.execute(update(Conta).where(Conta.id == conta_id).values(id=Conta.id))
    return sessao.get(Conta, conta_id, populate_existing=True)


def fazer_login(sessao, usuario, senha, origem):
    usuario = usuario.strip()
    reservar_tentativa_login(sessao, origem, usuario)
    conta = sessao.scalar(select(Conta).where(identidade_de_login(usuario)))
    if conta is None:
        autenticacao.calcular_hash_da_senha(senha, autenticacao.SAL_DE_USUARIO_INEXISTENTE)
        raise erro_autenticacao(autenticacao.MENSAGEM_LOGIN_INVALIDO)
    if not autenticacao.senha_confere(senha, conta) or not conta.ativo:
        raise erro_autenticacao(autenticacao.MENSAGEM_LOGIN_INVALIDO)

    hash_validado = conta.senha_hash
    conta = bloquear_conta(sessao, conta.id)
    if not conta.ativo or conta.senha_hash != hash_validado:
        raise erro_autenticacao(autenticacao.MENSAGEM_LOGIN_INVALIDO)
    agora = agora_utc()
    token = PREFIXO_SESSAO + secrets.token_urlsafe(32)
    expira_em = agora + autenticacao.VALIDADE_DO_TOKEN
    sessao.execute(delete(SessaoConta).where(SessaoConta.expira_em <= agora))
    sessao.add(SessaoConta(token_hash=autenticacao.hash_do_token(token), conta_id=conta.id, expira_em=expira_em))
    sessao.commit()
    return {
        "token": token,
        "expira_em": formatar_utc(expira_em),
        "usuario": usuario_json(conta),
        "empresas": [vinculo_json(empresa, vinculo.papel, permissoes_do_papel(sessao, empresa.id, vinculo.papel))
                     for empresa, vinculo in vinculos_ativos(sessao, conta.id)],
    }


def validar_senha(senha):
    if len(senha.strip()) < autenticacao.TAMANHO_MINIMO_DA_SENHA or len(senha) > 256:
        raise HTTPException(400, "Use uma senha de 12 a 256 caracteres, com ao menos 12 sem contar espaços nas pontas.")


def configurar_senha(conta, senha):
    validar_senha(senha)
    conta.sal = secrets.token_hex(16)
    conta.senha_hash = autenticacao.calcular_hash_da_senha(senha, conta.sal)


def trocar_senha(sessao, credenciais, senha_atual, nova_senha):
    _, conta = sessao_autenticada(sessao, credenciais)
    conta = bloquear_conta(sessao, conta.id)
    sessao_autenticada(sessao, credenciais)
    if not autenticacao.senha_confere(senha_atual, conta):
        raise erro_autenticacao(autenticacao.MENSAGEM_LOGIN_INVALIDO)
    configurar_senha(conta, nova_senha)
    sessao.execute(delete(SessaoConta).where(SessaoConta.conta_id == conta.id))
    sessao.commit()


def preparar_conta_inicial(sessao, nome, senha, empresa_nome):
    """Prepara o primeiro administrador na transação da migração e preserva alterações futuras."""
    inicial = sessao.get(ContaInicial, "principal")
    if inicial is not None:
        empresa = sessao.get(Empresa, inicial.empresa_id)
        conta = sessao.get(Conta, inicial.conta_id)
        if empresa is None or conta is None:
            raise ValueError("A configuração inicial referencia registros ausentes.")
        return empresa, conta
    nome = nome.strip()
    empresa_nome = empresa_nome.strip()
    if not nome or not empresa_nome:
        raise ValueError("Informe a conta e a empresa iniciais.")
    email = normalizar_email(nome) if "@" in nome else None
    empresa = sessao.scalar(select(Empresa).where(Empresa.nome == empresa_nome))
    conta = sessao.scalar(select(Conta).where(identidade_de_login(nome)))
    if empresa is not None or conta is not None:
        if empresa is not None and conta is not None and conta.plataforma:
            vinculo = sessao.get(VinculoConta, (conta.id, empresa.id))
            if vinculo is not None:
                sessao.add(ContaInicial(chave="principal", empresa_id=empresa.id, conta_id=conta.id))
                sessao.flush()
                return empresa, conta
        raise ValueError("A empresa ou conta inicial já existe sem o vínculo esperado.")

    empresa = Empresa(nome=empresa_nome)
    conta = Conta(nome=nome, email=email, plataforma=True)
    configurar_senha(conta, senha)
    sessao.add_all((empresa, conta))
    sessao.flush()
    sessao.add(VinculoConta(conta_id=conta.id, empresa_id=empresa.id, papel=ADMINISTRADOR))
    sessao.add(ContaInicial(chave="principal", empresa_id=empresa.id, conta_id=conta.id))
    sessao.flush()
    return empresa, conta


def normalizar_email(email):
    email = email.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise HTTPException(400, "Informe um e-mail válido.")
    return email


def identidade_de_login(usuario):
    if "@" in usuario:
        return Conta.email == usuario.casefold()
    return (Conta.nome == usuario) & Conta.email.is_(None)


def bloquear_empresa(sessao, empresa_id):
    # Serializa alterações de equipe, suspensão e aceites dentro da empresa.
    sessao.execute(update(Empresa).where(Empresa.id == empresa_id).values(id=Empresa.id))
    empresa = sessao.get(Empresa, empresa_id, populate_existing=True)
    if empresa is None:
        raise HTTPException(404, "Empresa não encontrada.")
    return empresa


def bloquear_administracao(sessao, contexto):
    exigir(contexto, "administrar")
    empresa = bloquear_empresa(sessao, contexto.empresa.id)
    vinculo = sessao.get(VinculoConta, (contexto.conta.id, empresa.id), populate_existing=True)
    if not empresa.ativo or vinculo is None or not vinculo.ativo or vinculo.papel != ADMINISTRADOR:
        raise HTTPException(403, "Sua conta não administra esta empresa.")
    return empresa


def gravar(sessao, mensagem_conflito):
    try:
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        raise HTTPException(409, mensagem_conflito) from erro


def registrar_evento(sessao, empresa_id, autor_id, acao, **dados):
    sessao.add(EventoAcesso(empresa_id=empresa_id, autor_id=autor_id, acao=acao,
                          dados=dados, registrado_em=agora_utc()))


def tem_administrador(sessao, empresa_id, excluir_conta=None):
    consulta = (
        select(VinculoConta.conta_id).join(Conta, VinculoConta.conta_id == Conta.id)
        .where(VinculoConta.empresa_id == empresa_id, VinculoConta.papel == ADMINISTRADOR,
               VinculoConta.ativo.is_(True), Conta.ativo.is_(True))
    )
    if excluir_conta is not None:
        consulta = consulta.where(VinculoConta.conta_id != excluir_conta)
    return sessao.scalar(consulta.limit(1)) is not None


def membro_json(conta, vinculo, permissoes):
    return {"id": conta.id, "nome": conta.nome, "email": conta.email, "papel": vinculo.papel,
            "ativo": vinculo.ativo and conta.ativo,
            "permissoes": sorted(permissoes) if vinculo.ativo and conta.ativo else []}


def listar_equipe(sessao, contexto):
    exigir(contexto, "administrar")
    membros = sessao.execute(
        select(Conta, VinculoConta).join(VinculoConta, VinculoConta.conta_id == Conta.id)
        .where(VinculoConta.empresa_id == contexto.empresa.id).order_by(Conta.nome)
    )
    direitos = {papel: permissoes_do_papel(sessao, contexto.empresa.id, papel) for papel in PAPEIS}
    return [membro_json(conta, vinculo, direitos[vinculo.papel]) for conta, vinculo in membros]


def alterar_membro(sessao, contexto, conta_id, alteracoes):
    empresa = bloquear_administracao(sessao, contexto)
    vinculo = sessao.get(VinculoConta, (conta_id, empresa.id))
    if vinculo is None:
        raise HTTPException(404, "Participante não encontrado nesta empresa.")
    conta = sessao.get(Conta, conta_id)
    anterior = {"papel": vinculo.papel, "ativo": vinculo.ativo}
    for campo, valor in alteracoes.items():
        setattr(vinculo, campo, valor)
    if anterior["ativo"] and anterior["papel"] == ADMINISTRADOR and (not vinculo.ativo or vinculo.papel != ADMINISTRADOR):
        if not tem_administrador(sessao, empresa.id, excluir_conta=conta_id):
            raise HTTPException(409, "Indique outro administrador antes de alterar o último administrador ativo.")
    registrar_evento(sessao, empresa.id, contexto.conta.id, "alterar_vinculo", conta_id=conta_id,
                     anterior=anterior, atual={"papel": vinculo.papel, "ativo": vinculo.ativo})
    sessao.commit()
    return membro_json(conta, vinculo, permissoes_do_papel(sessao, empresa.id, vinculo.papel))


def papel_json(sessao, empresa_id, papel):
    return {"papel": papel, "permissoes": sorted(permissoes_do_papel(sessao, empresa_id, papel)),
            "limite": sorted(PAPEIS[papel])}


def alterar_permissoes_do_papel(sessao, contexto, papel, permissoes):
    empresa = bloquear_administracao(sessao, contexto)
    if papel == ADMINISTRADOR:
        raise HTTPException(409, "O papel de administrador mantém as permissões necessárias à gestão da empresa.")
    if not permissoes <= PAPEIS[papel]:
        raise HTTPException(400, "Selecione permissões dentro do limite deste papel.")
    anterior = permissoes_do_papel(sessao, empresa.id, papel)
    registro = sessao.get(PermissoesPapel, (empresa.id, papel))
    if registro is None:
        registro = PermissoesPapel(empresa_id=empresa.id, papel=papel)
        sessao.add(registro)
    registro.permissoes = sorted(permissoes)
    registrar_evento(sessao, empresa.id, contexto.conta.id, "alterar_permissoes_papel", papel=papel,
                     anterior=sorted(anterior), atual=registro.permissoes)
    sessao.commit()
    return papel_json(sessao, empresa.id, papel)


def convite_json(convite):
    return {"id": convite.id, "email": convite.email, "papel": convite.papel,
            "expira_em": formatar_utc(convite.expira_em), "usado_em": formatar_utc(convite.usado_em),
            "revogado_em": formatar_utc(convite.revogado_em)}


def emitir_convite(sessao, empresa, autor, email, papel, *, primeiro_administrador=False):
    email = normalizar_email(email)
    conta_id = sessao.scalar(select(Conta.id).where(Conta.email == email))
    if conta_id is not None:
        vinculo = sessao.get(VinculoConta, (conta_id, empresa.id))
        if vinculo is not None and vinculo.ativo:
            raise HTTPException(409, "Este destinatário já tem vínculo ativo com a empresa.")
    agora = agora_utc()
    substituir = ConviteConta.primeiro_administrador.is_(True) if primeiro_administrador else ConviteConta.email == email
    sessao.execute(update(ConviteConta).where(ConviteConta.empresa_id == empresa.id, substituir,
                                            ConviteConta.usado_em.is_(None), ConviteConta.revogado_em.is_(None),
                                            ConviteConta.expira_em > agora).values(revogado_em=agora))
    token = PREFIXO_CONVITE + secrets.token_urlsafe(32)
    convite = ConviteConta(token_hash=autenticacao.hash_do_token(token), empresa_id=empresa.id, email=email,
                          papel=papel, expira_em=agora + VALIDADE_CONVITE, primeiro_administrador=primeiro_administrador)
    sessao.add(convite)
    sessao.flush()
    registrar_evento(sessao, empresa.id, autor.id, "emitir_convite", convite_id=convite.id, papel=papel)
    sessao.commit()
    return {"convite": convite_json(convite), "token": token}


def aceitar_convite(sessao, token, email, nome, senha, credenciais):
    email = normalizar_email(email)
    consulta = select(ConviteConta).where(ConviteConta.token_hash == autenticacao.hash_do_token(token))
    convite = sessao.scalar(consulta) if token.startswith(PREFIXO_CONVITE) else None
    if convite is None or convite.email != email:
        raise HTTPException(400, "Convite inválido ou destinado a outro e-mail.")
    empresa = bloquear_empresa(sessao, convite.empresa_id)
    sessao.refresh(convite)
    agora = agora_utc()
    if not empresa.ativo or convite.revogado_em or convite.usado_em or convite.expira_em <= agora:
        raise HTTPException(409, "Este convite já foi usado, expirou ou está indisponível.")
    if convite.primeiro_administrador and tem_administrador(sessao, empresa.id):
        raise HTTPException(409, "Esta empresa já possui administrador ativo.")

    conta = sessao.scalar(select(Conta).where(Conta.email == email))
    if conta is not None:
        if sessao_autenticada(sessao, credenciais)[1].id != conta.id:
            raise HTTPException(403, "Entre com a conta do destinatário para aceitar o convite.")
    else:
        if credenciais is not None or not nome or not nome.strip() or senha is None:
            raise HTTPException(400, "Informe seu nome e crie uma senha para aceitar o convite.")
        conta = Conta(nome=nome.strip(), email=email)
        configurar_senha(conta, senha)
        sessao.add(conta)
        try:
            sessao.flush()
        except IntegrityError as erro:
            sessao.rollback()
            raise HTTPException(409, "Já existe uma conta com este e-mail.") from erro

    vinculo = sessao.get(VinculoConta, (conta.id, empresa.id))
    if vinculo is not None and vinculo.ativo:
        raise HTTPException(409, "Já existe um vínculo ativo para este convite.")
    if vinculo is None:
        vinculo = VinculoConta(conta_id=conta.id, empresa_id=empresa.id)
        sessao.add(vinculo)
    vinculo.papel = convite.papel
    vinculo.ativo = True
    convite.usado_em = agora
    registrar_evento(sessao, empresa.id, conta.id, "aceitar_convite", convite_id=convite.id, papel=vinculo.papel)
    sessao.commit()
    permissoes = permissoes_do_papel(sessao, empresa.id, vinculo.papel)
    return {"usuario": usuario_json(conta), "empresa": vinculo_json(empresa, vinculo.papel, permissoes)}


def integracao_json(integracao):
    return {"id": integracao.id, "nome": integracao.nome, "permissoes": integracao.permissoes,
            "recurso_tipo": integracao.recurso_tipo, "recurso_id": integracao.recurso_id,
            "expira_em": formatar_utc(integracao.expira_em), "revogado_em": formatar_utc(integracao.revogado_em),
            "ultimo_uso_em": formatar_utc(integracao.ultimo_uso_em)}


def criar_integracao(sessao, contexto, dados):
    empresa = bloquear_administracao(sessao, contexto)
    expira_em = para_utc(dados.expira_em)
    agora = agora_utc()
    if not agora < expira_em <= agora + VALIDADE_MAXIMA_INTEGRACAO:
        raise HTTPException(400, "Escolha uma validade futura de até 365 dias.")
    if bool(dados.recurso_tipo) != bool(dados.recurso_id):
        raise HTTPException(400, "Informe o tipo e o identificador para restringir o recurso.")
    token = PREFIXO_INTEGRACAO + secrets.token_urlsafe(32)
    integracao = Integracao(empresa_id=empresa.id, nome=dados.nome, permissoes=sorted(dados.permissoes),
                            recurso_tipo=dados.recurso_tipo, recurso_id=dados.recurso_id,
                            expira_em=expira_em, token_hash=autenticacao.hash_do_token(token))
    sessao.add(integracao)
    sessao.flush()
    registrar_evento(sessao, empresa.id, contexto.conta.id, "criar_integracao", integracao_id=integracao.id)
    sessao.commit()
    return {**integracao_json(integracao), "token": token}


def revogar_integracao(sessao, contexto, integracao_id):
    empresa = bloquear_administracao(sessao, contexto)
    integracao = sessao.scalar(select(Integracao).where(Integracao.id == integracao_id,
                                                       Integracao.empresa_id == empresa.id))
    if integracao is None:
        raise HTTPException(404, "Integração não encontrada nesta empresa.")
    if integracao.revogado_em is None:
        integracao.revogado_em = agora_utc()
        registrar_evento(sessao, empresa.id, contexto.conta.id, "revogar_integracao", integracao_id=integracao.id)
        sessao.commit()
