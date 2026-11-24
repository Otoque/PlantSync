from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .audit_log import log_security_block
from .models import User
from .ownership import get_owned_device_or_403
from .totp_service import (
    setup_user_2fa,
    verify_and_consume_recovery_code,
    verify_user_totp,
)

router = APIRouter()


class TwoFactorVerifyRequest(BaseModel):
    mfa_token: str
    otp_code: str | None = None
    recovery_code: str | None = None


class DeviceConfigUpdate(BaseModel):
    name: str


# Substitua estas dependências pelas funções reais da sua sessão/JWT
def get_db() -> Session: ...
def get_current_user() -> User: ...
def verify_password(plain: str, hashed: str) -> bool: ...
def create_mfa_temp_token(user_id: int) -> str: ...
def decode_mfa_temp_token(token: str) -> int: ...
def create_access_token(user_id: int) -> str: ...


@router.post("/auth/login")
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        log_security_block(
            control="AUTH", reason="credenciais_invalidas", user_id=username
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas."
        )

    if user.totp_enabled:
        return {
            "mfa_required": True,
            "mfa_token": create_mfa_temp_token(user.id),
        }

    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.post("/auth/2fa/verify-login")
def verify_2fa_login(payload: TwoFactorVerifyRequest, db: Session = Depends(get_db)):
    user_id = decode_mfa_temp_token(payload.mfa_token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão MFA inválida."
        )

    if payload.otp_code:
        ok, reason = verify_user_totp(db, user, payload.otp_code)
    elif payload.recovery_code:
        ok, reason = verify_and_consume_recovery_code(db, user, payload.recovery_code)
    else:
        ok, reason = False, "segundo_fator_ausente"

    if not ok:
        log_security_block(control="2FA", reason=reason, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Falha na verificação 2FA."
        )

    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.post("/auth/2fa/setup")
def setup_2fa(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return setup_user_2fa(db, current_user)


@router.post("/auth/2fa/confirm")
def confirm_2fa(
    otp_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok, reason = verify_user_totp(db, current_user, otp_code)
    if not ok:
        log_security_block(control="2FA_SETUP", reason=reason, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Código OTP inválido."
        )

    current_user.totp_enabled = True
    db.commit()
    return {"status": "2FA ativado com sucesso"}


@router.get("/devices/{device_id}")
def read_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = get_owned_device_or_403(db, current_user, device_id)
    return {"id": device.id, "name": device.name, "channel": device.thingspeak_channel}


@router.patch("/devices/{device_id}/config")
def update_device_config(
    device_id: int,
    body: DeviceConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = get_owned_device_or_403(db, current_user, device_id)
    device.name = body.name
    db.commit()
    return {"id": device.id, "name": device.name}
