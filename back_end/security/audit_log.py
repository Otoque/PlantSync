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


def get_totp_window() -> int:
    return int(os.getenv("PLANTSYNC_TOTP_WINDOW", "1"))


def get_totp_key() -> str:
    return os.getenv("PLANTSYNC_TOTP_KEY", "")


def log_security_block(
    control: str,
    reason: str,
    user_id: int | str | None = None,
    resource_id: int | str | None = None,
) -> None:
    code = get_mission_code()
    mensagem = f"[MISSAO:{code}][BLOQUEIO][{control}] motivo={reason} | user_id={user_id} | resource_id={resource_id}"
    logger.warning(mensagem)
    # Garante visibilidade imediata em saídas capturadas
    sys.stderr.write(mensagem + "\n")
    sys.stderr.flush()
