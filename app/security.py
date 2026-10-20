"""Пароли (argon2id), сессии в cookie, CSRF и ограничение попыток входа."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db
from .timeutil import utcnow

SESSION_COOKIE = "feel_session"
CSRF_COOKIE = "feel_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_hasher = PasswordHasher()  # argon2id по умолчанию


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for(session_token: str) -> str:
    return hmac.new(settings.secret_key.encode(), session_token.encode(), hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Сессии
# --------------------------------------------------------------------------- #
def create_session(db: Session, user: models.User, user_agent: Optional[str]) -> str:
    token = secrets.token_urlsafe(32)
    db.add(models.UserSession(
        user_id=user.id,
        token_hash=sha256(token),
        user_agent=(user_agent or "")[:500],
        expires_at=utcnow() + timedelta(days=settings.session_days),
    ))
    db.commit()
    return token


def set_session_cookies(response, token: str) -> None:
    max_age = settings.session_days * 86400
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    # CSRF-токен читается скриптом и отправляется в заголовке X-CSRF-Token.
    response.set_cookie(CSRF_COOKIE, csrf_for(token), max_age=max_age, httponly=False,
                        secure=settings.cookie_secure, samesite="lax", path="/")


def clear_session_cookies(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def drop_session(db: Session, token: Optional[str]) -> None:
    if token:
        db.execute(delete(models.UserSession).where(models.UserSession.token_hash == sha256(token)))
        db.commit()


def _user_from_request(request: Request, db: Session) -> Optional[models.User]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.scalar(select(models.UserSession).where(models.UserSession.token_hash == sha256(token)))
    if sess is None or sess.expires_at < utcnow():
        return None
    return db.get(models.User, sess.user_id)


def check_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    token = request.cookies.get(SESSION_COOKIE)
    sent = request.headers.get(CSRF_HEADER, "")
    if not token or not sent or not hmac.compare_digest(sent, csrf_for(token)):
        raise HTTPException(status_code=403, detail="Ошибка проверки CSRF, обновите страницу")


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user = _user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Нужно войти")
    check_csrf(request)
    return user


def require_same_origin_header(request: Request) -> None:
    """Для запросов без сессии (вход): нестандартный заголовок нельзя отправить
    с чужого сайта без CORS, а CORS мы не разрешаем."""
    if request.headers.get("x-requested-with") != "feel":
        raise HTTPException(status_code=403, detail="Запрос отклонён")


# --------------------------------------------------------------------------- #
# Ограничение попыток входа: не больше N неудачных за окно на пару email + IP
# --------------------------------------------------------------------------- #
def _attempt_key(email: str, ip: str) -> str:
    return sha256(f"{email.strip().lower()}|{ip}")


def login_blocked(db: Session, email: str, ip: str) -> bool:
    since = utcnow() - timedelta(minutes=settings.login_window_min)
    db.execute(delete(models.LoginAttempt).where(models.LoginAttempt.created_at < since))
    count = db.scalar(select(func.count()).select_from(models.LoginAttempt).where(
        models.LoginAttempt.key_hash == _attempt_key(email, ip),
        models.LoginAttempt.created_at >= since,
    ))
    db.commit()
    return count >= settings.login_max_attempts


def record_failed_login(db: Session, email: str, ip: str) -> None:
    db.add(models.LoginAttempt(key_hash=_attempt_key(email, ip)))
    db.commit()


def clear_failed_logins(db: Session, email: str, ip: str) -> None:
    db.execute(delete(models.LoginAttempt).where(
        models.LoginAttempt.key_hash == _attempt_key(email, ip)))
    db.commit()


def client_ip(request: Request) -> str:
    # Берём последний адрес: его дописал прокси хостинга, остальные мог подставить клиент.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
