"""
Login simples com usuario e senha, sem perfis.

- Senha: guardada so como hash com sal (scrypt, da biblioteca padrao do Python).
- Acesso: um token aleatorio com validade, enviado em "Authorization: Bearer".
  No banco fica so o hash do token, entao quem ler o banco nao consegue entrar.
- Usuario: nao ha cadastro pela API. O unico usuario vem das variaveis de ambiente
  PLANTSYNC_USUARIO e PLANTSYNC_SENHA, lidas quando o servidor liga.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from models.tabelas import TokenDeAcesso, Usuario
from services.datas import agora_utc, formatar_utc
from services.erros import ErroNaoAutenticado

VALIDADE_DO_TOKEN = timedelta(hours=8)
MENSAGEM_LOGIN_INVALIDO = "Usuário ou senha inválidos."
MENSAGEM_SEM_LOGIN = "Faça login para continuar."

# Custo do scrypt: uma das opcoes recomendadas pelo guia de senhas da OWASP
# (Password Storage Cheat Sheet). Usa 16 MiB de memoria e leva cerca de 0,2 s.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 5

# 16 bytes escritos em hexadecimal, usados so para gastar o mesmo tempo
# quando o usuario nao existe.
SAL_DE_USUARIO_INEXISTENTE = "00" * 16

logger = logging.getLogger("plantsync")


def calcular_hash_da_senha(senha, sal):
    """scrypt e lento de proposito: dificulta testar milhoes de senhas se o banco vazar."""
    resultado = hashlib.scrypt(
        senha.encode("utf-8"),
        salt=bytes.fromhex(sal),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return resultado.hex()


def senha_confere(senha, usuario):
    calculado = calcular_hash_da_senha(senha, usuario.sal)
    # compare_digest leva o mesmo tempo mesmo se os textos diferem logo no comeco.
    return hmac.compare_digest(calculado, usuario.senha_hash)


def hash_do_token(token):
    """O token ja e aleatorio e longo, entao um hash simples basta (nao precisa de sal)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cadastrar_usuario(sessao, nome, senha):
    sal = secrets.token_hex(16)
    sessao.add(Usuario(nome=nome, sal=sal, senha_hash=calcular_hash_da_senha(senha, sal)))
    sessao.commit()


def criar_token_de_acesso(sessao, usuario):
    """Cria o token de acesso. O token em si so existe na resposta ao usuario."""
    token = secrets.token_urlsafe(32)
    expira_em = agora_utc() + VALIDADE_DO_TOKEN
    sessao.add(TokenDeAcesso(
        token_hash=hash_do_token(token),
        usuario_id=usuario.id,
        expira_em=expira_em,
    ))
    sessao.commit()
    return {"token": token, "expira_em": formatar_utc(expira_em)}


def apagar_tokens_vencidos(sessao):
    """Limpeza de passagem, a cada login, para a tabela nao crescer sem parar."""
    sessao.query(TokenDeAcesso).filter(TokenDeAcesso.expira_em <= agora_utc()).delete()


def fazer_login(sessao, nome, senha):
    """Confere usuario e senha. A resposta de erro nao diz qual dos dois esta errado."""
    usuario = sessao.query(Usuario).filter(Usuario.nome == nome).first()
    if usuario is None:
        # Calcula o hash mesmo assim: sem isso, a resposta sairia mais rapido
        # e revelaria quais usuarios existem.
        calcular_hash_da_senha(senha, SAL_DE_USUARIO_INEXISTENTE)
        raise ErroNaoAutenticado(MENSAGEM_LOGIN_INVALIDO)
    if not senha_confere(senha, usuario):
        raise ErroNaoAutenticado(MENSAGEM_LOGIN_INVALIDO)

    apagar_tokens_vencidos(sessao)
    return criar_token_de_acesso(sessao, usuario)


def conferir_token(sessao, token):
    """
    Levanta ErroNaoAutenticado se o token nao existir ou tiver vencido.
    O token vencido tambem e apagado do banco.
    """
    linha = sessao.get(TokenDeAcesso, hash_do_token(token))
    if linha is None:
        raise ErroNaoAutenticado(MENSAGEM_SEM_LOGIN)
    if linha.expira_em <= agora_utc():
        sessao.delete(linha)
        sessao.commit()
        raise ErroNaoAutenticado(MENSAGEM_SEM_LOGIN)


def encerrar_token_de_acesso(sessao, token):
    linha = sessao.get(TokenDeAcesso, hash_do_token(token))
    sessao.delete(linha)
    sessao.commit()


def usuario_ja_esta_correto(sessao, nome, senha):
    """Diz se o banco ja tem o usuario das variaveis de ambiente, com a mesma senha."""
    if not nome or not senha:
        return False
    usuario = sessao.query(Usuario).filter(Usuario.nome == nome).first()
    if usuario is None:
        return False
    return senha_confere(senha, usuario)


def apagar_usuarios_e_tokens(sessao):
    sessao.query(TokenDeAcesso).delete()
    sessao.query(Usuario).delete()
    sessao.commit()


def preparar_usuario_inicial(sessao, nome, senha):
    """
    Deixa o banco igual as variaveis de ambiente, ao ligar o servidor. Como nao ha
    cadastro pela API, o usuario delas e o unico: se ele mudou, ou se elas sumiram,
    o usuario antigo e os tokens abertos deixam de valer.
    """
    if usuario_ja_esta_correto(sessao, nome, senha):
        return

    apagar_usuarios_e_tokens(sessao)
    if nome and senha:
        cadastrar_usuario(sessao, nome, senha)
    else:
        logger.warning(
            "PLANTSYNC_USUARIO e PLANTSYNC_SENHA nao foram definidas: "
            "a API esta no ar, mas ninguem consegue entrar."
        )
