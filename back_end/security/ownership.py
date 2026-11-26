"""Controle de acesso baseado em posse / empresa (Proteção contra IDOR)."""

from fastapi import HTTPException, status
from .audit_log import log_security_block


def validar_posse(
    recurso_empresa_id: int,
    empresa_id_contexto: int,
    tipo_recurso: str,
    identificador_recurso: str | int | None = None,
    user_id: int | str | None = None,
    status_code: int = status.HTTP_404_NOT_FOUND,
) -> None:
    # None == None passaria na comparacao: empresa desconhecida tambem e negada.
    if (
        recurso_empresa_id is None
        or empresa_id_contexto is None
        or recurso_empresa_id != empresa_id_contexto
    ):
        log_security_block(
            control="IDOR",
            reason=f"tentativa_acesso_{tipo_recurso}_alheio",
            user_id=user_id,
            resource_id=identificador_recurso,
        )
        raise HTTPException(
            status_code=status_code,
            detail=f"{tipo_recurso.capitalize()} indisponível.",
        )
