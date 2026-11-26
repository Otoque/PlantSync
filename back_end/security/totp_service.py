import hashlib
import secrets
import time
from datetime import timedelta
import pyotp
from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.contas import CodigoRecuperacaoConta, Conta, SessaoMfaConta
from services import autenticacao
from services.datas import agora_utc
from .audit_log import get_totp_key, get_totp_window

PREFIXO_MFA = "psm_"
DURACAO_MFA_TOKEN = timedelta(minutes=5)


def _get_cipher() -> Fernet:
    chave = get_totp_key()
    if not chave:
        raise RuntimeError("PLANTSYNC_TOTP_KEY não configurada no ambiente.")
    return Fernet(chave.encode() if isinstance(chave, str) else chave)


def encrypt_secret(plain_secret: str) -> str:
    return _get_cipher().encrypt(plain_secret.encode()).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    return _get_cipher().decrypt(encrypted_secret.encode()).decode()


def _hash_recovery_code(plain_code: str) -> str:
    normalized = plain_code.strip().upper().replace("-", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_recovery_codes(sessao: Session, conta: Conta, count: int = 8) -> list[str]:
    # Invalida códigos antigos antes de gerar novos
    sessao.execute(
        delete(CodigoRecuperacaoConta).where(CodigoRecuperacaoConta.conta_id == conta.id)
    )

    plain_codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()  # 8 caracteres hex
        formatted = f"{raw[:4]}-{raw[4:]}"
        plain_codes.append(formatted)
        sessao.add(
            CodigoRecuperacaoConta(
                conta_id=conta.id,
                codigo_hash=_hash_recovery_code(formatted),
            )
        )

    sessao.flush()
    return plain_codes


def setup_user_2fa(sessao: Session, conta: Conta, issuer: str = "PlantSync") -> dict:
    plain_secret = pyotp.random_base32()
    conta.totp_secret_encrypted = encrypt_secret(plain_secret)
    conta.totp_enabled = False
    conta.totp_last_timestep = None

    user_label = conta.email or conta.nome
    totp = pyotp.TOTP(plain_secret)
    provisioning_uri = totp.provisioning_uri(name=user_label, issuer_name=issuer)
    recovery_codes = generate_recovery_codes(sessao, conta)
    sessao.commit()

    return {
        "provisioning_uri": provisioning_uri,
        "recovery_codes": recovery_codes,
    }


def verify_user_totp(
    sessao: Session, conta: Conta, code: str, check_only: bool = False
) -> tuple[bool, str]:
    if not conta.totp_secret_encrypted:
        return False, "2fa_nao_configurado"

    clean_code = (code or "").strip()
    if not clean_code.isdigit() or len(clean_code) != 6:
        return False, "formato_otp_invalido"

    try:
        plain_secret = decrypt_secret(conta.totp_secret_encrypted)
    except Exception:
        return False, "erro_decriptacao_segredo_totp"

    totp = pyotp.TOTP(plain_secret)
    window = get_totp_window()

    # Valida dentro da janela configurada (padrão: +-1 intervalo de 30s)
    if not totp.verify(clean_code, valid_window=window):
        return False, "codigo_otp_invalido_ou_expirado"

    # Proteção anti-replay do mesmo token TOTP na mesma janela de tempo
    current_timestep = int(time.time()) // totp.interval
    if (
        conta.totp_last_timestep is not None
        and current_timestep <= conta.totp_last_timestep
    ):
        return False, "codigo_otp_ja_utilizado"

    if not check_only:
        conta.totp_last_timestep = current_timestep
        sessao.commit()

    return True, "ok"


def confirm_user_2fa(sessao: Session, conta: Conta, otp_code: str) -> tuple[bool, str]:
    ok, reason = verify_user_totp(sessao, conta, otp_code, check_only=True)
    if not ok:
        return False, reason
    conta.totp_enabled = True
    conta.totp_last_timestep = None
    sessao.commit()
    return True, "ok"


def disable_user_2fa(sessao: Session, conta: Conta) -> None:
    """Desliga o 2FA e apaga segredo e codigos de recuperacao, que nao podem sobrar validos."""
    conta.totp_enabled = False
    conta.totp_secret_encrypted = None
    conta.totp_last_timestep = None
    sessao.execute(
        delete(CodigoRecuperacaoConta).where(CodigoRecuperacaoConta.conta_id == conta.id)
    )
    sessao.commit()


def verify_and_consume_recovery_code(
    sessao: Session, conta: Conta, plain_code: str
) -> tuple[bool, str]:
    if not plain_code:
        return False, "codigo_recuperacao_ausente"

    target_hash = _hash_recovery_code(plain_code)
    record = sessao.scalar(
        select(CodigoRecuperacaoConta).where(
            CodigoRecuperacaoConta.conta_id == conta.id,
            CodigoRecuperacaoConta.codigo_hash == target_hash,
        )
    )

    if not record:
        return False, "codigo_recuperacao_invalido"
    if record.usado_em is not None:
        return False, "codigo_recuperacao_ja_utilizado"

    record.usado_em = agora_utc()
    sessao.commit()
    return True, "ok"


def criar_mfa_token(sessao: Session, conta: Conta) -> str:
    agora = agora_utc()
    token = PREFIXO_MFA + secrets.token_urlsafe(32)
    expira_em = agora + DURACAO_MFA_TOKEN
    sessao.execute(
        delete(SessaoMfaConta).where(
            (SessaoMfaConta.expira_em <= agora) | (SessaoMfaConta.conta_id == conta.id)
        )
    )
    sessao.add(
        SessaoMfaConta(
            token_hash=autenticacao.hash_do_token(token),
            conta_id=conta.id,
            expira_em=expira_em,
        )
    )
    sessao.commit()
    return token


def consumir_mfa_token(sessao: Session, token: str) -> Conta | None:
    if not token or not token.startswith(PREFIXO_MFA):
        return None
    agora = agora_utc()
    token_hash = autenticacao.hash_do_token(token)
    sessao_mfa = sessao.get(SessaoMfaConta, token_hash)
    if sessao_mfa is None or sessao_mfa.expira_em <= agora:
        return None
    conta = sessao.get(Conta, sessao_mfa.conta_id)
    sessao.delete(sessao_mfa)
    sessao.commit()
    return conta
