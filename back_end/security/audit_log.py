import logging
import os
import sys

logger = logging.getLogger("plantsync.security")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def get_mission_code() -> str:
    return os.getenv("PLANTSYNC_CODIGO_MISSAO", "XXXXXX")


# Cada passo da janela aceita mais 30 s de codigos antigos/futuros; acima de 2
# o 2FA fica facil demais de adivinhar, entao o valor e limitado.
JANELA_TOTP_PADRAO = 1
JANELA_TOTP_MAXIMA = 2


def get_totp_window() -> int:
    try:
        janela = int(os.getenv("PLANTSYNC_TOTP_WINDOW", str(JANELA_TOTP_PADRAO)))
    except ValueError:
        return JANELA_TOTP_PADRAO
    return max(0, min(janela, JANELA_TOTP_MAXIMA))


def get_totp_key() -> str:
    return os.getenv("PLANTSYNC_TOTP_KEY", "")


def _limpar_para_log(valor) -> str:
    """Troca quebras de linha e caracteres de controle para evitar linhas falsas no log."""
    texto = str(valor)
    return "".join(c if c.isprintable() else "?" for c in texto)[:200]


def log_security_block(
    control: str,
    reason: str,
    user_id: int | str | None = None,
    resource_id: int | str | None = None,
) -> None:
    code = get_mission_code()
    control, reason, user_id, resource_id = (
        _limpar_para_log(v) for v in (control, reason, user_id, resource_id)
    )
    mensagem = f"[MISSAO:{code}][BLOQUEIO][{control}] motivo={reason} | user_id={user_id} | resource_id={resource_id}"
    logger.warning(mensagem)
    # Garante visibilidade imediata em saídas capturadas
    sys.stderr.write(mensagem + "\n")
    sys.stderr.flush()
