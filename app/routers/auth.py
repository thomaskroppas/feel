"""Вход, выход, текущий пользователь, удаление данных."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..db import get_db
from ..services.users import create_user, wipe_user_data

router = APIRouter(prefix="/api", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class PasswordConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _me(user: models.User) -> dict:
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    security.require_same_origin_header(request)
    email = body.email.strip().lower()
    ip = security.client_ip(request)
    if security.login_blocked(db, email, ip):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте через 15 минут")
    user = db.scalar(select(models.User).where(models.User.email == email))
    if user is None or not security.verify_password(body.password, user.password_hash):
        security.record_failed_login(db, email, ip)
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    security.clear_failed_logins(db, email, ip)
    token = security.create_session(db, user, request.headers.get("user-agent"))
    security.set_session_cookies(response, token)
    return _me(user)


@router.post("/auth/register")
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    security.require_same_origin_header(request)
    if not settings.registration_open:
        raise HTTPException(status_code=403, detail="Регистрация закрыта")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Пароль — не короче 8 символов")
    try:
        user = create_user(db, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = security.create_session(db, user, request.headers.get("user-agent"))
    security.set_session_cookies(response, token)
    return _me(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: models.User = Depends(security.current_user)):
    security.drop_session(db, request.cookies.get(security.SESSION_COOKIE))
    security.clear_session_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
def me(user: models.User = Depends(security.current_user)):
    return _me(user)


@router.get("/auth/config")
def auth_config():
    return {"registration_open": settings.registration_open}


@router.post("/account/wipe")
def wipe(body: PasswordConfirm, db: Session = Depends(get_db),
         user: models.User = Depends(security.current_user)):
    if not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Неверный пароль")
    wipe_user_data(db, user.id)
    return {"ok": True}
