"""Conversoes de data e hora usadas pela API."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FUSO_RECIFE = ZoneInfo("America/Recife")


def agora_utc():
    """Horario atual em UTC, sem fuso, no mesmo formato gravado no banco."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def para_utc(data):
    """
    Converte uma data recebida para UTC sem fuso.
    Data sem fuso e considerada como ja estando em UTC.
    """
    if data.tzinfo is None:
        return data
    return data.astimezone(timezone.utc).replace(tzinfo=None)


def formatar_utc(data):
    """Formato do contrato: 2026-10-25T17:30:00Z. None continua None."""
    if data is None:
        return None
    return data.strftime("%Y-%m-%dT%H:%M:%SZ")


def hora_recife(data):
    """Texto com hora e dia no horario de Recife, ex.: '18:00 de 24/10'."""
    local = data.replace(tzinfo=timezone.utc).astimezone(FUSO_RECIFE)
    return local.strftime("%H:%M de %d/%m")
