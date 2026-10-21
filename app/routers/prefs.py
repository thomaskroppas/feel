"""Настройки пользователя и подписки на уведомления."""
import re
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..security import current_user
from ..services import push
from ..services.days import evening_done, morning_done
from ..timeutil import all_timezones, is_valid_tz, local_date_of, utcnow

router = APIRouter(prefix="/api", tags=["prefs"])

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SETTINGS_FIELDS = ("timezone", "morning_enabled", "morning_time", "morning_text",
                   "evening_enabled", "evening_time", "evening_text",
                   "repeat_enabled", "repeat_after_min")


class SettingsIn(BaseModel):
    timezone: Optional[str] = Field(default=None, max_length=64)
    morning_enabled: Optional[bool] = None
    morning_time: Optional[str] = None
    morning_text: Optional[str] = Field(default=None, min_length=1, max_length=200)
    evening_enabled: Optional[bool] = None
    evening_time: Optional[str] = None
    evening_text: Optional[str] = Field(default=None, min_length=1, max_length=200)
    repeat_enabled: Optional[bool] = None
    repeat_after_min: Optional[int] = Field(default=None, ge=15, le=240)

    @field_validator("morning_time", "evening_time")
    @classmethod
    def _time(cls, v):
        if v is not None and not HHMM.match(v):
            raise ValueError("Время в формате ЧЧ:ММ")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None and not is_valid_tz(v):
            raise ValueError("Неизвестный часовой пояс")
        return v

    @field_validator("morning_text", "evening_text")
    @classmethod
    def _text(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Текст не может быть пустым")
        return v.strip() if v else v


def _out(st: models.UserSettings) -> dict:
    return {f: getattr(st, f) for f in SETTINGS_FIELDS}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return _out(db.get(models.UserSettings, user.id))


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db),
                 user: models.User = Depends(current_user)):
    st = db.get(models.UserSettings, user.id)
    changes = {f: v for f, v in body.model_dump(exclude_unset=True).items() if v is not None}
    # Новое время утра или вечера — сегодняшнее уведомление можно получить заново.
    retime = [k for k in ("morning", "evening")
              if f"{k}_time" in changes and changes[f"{k}_time"] != getattr(st, f"{k}_time")]
    for field, value in changes.items():
        setattr(st, field, value)
    if retime:
        today = local_date_of(utcnow(), st.timezone)
        kinds = retime + [f"{k}_repeat" for k in retime]
        db.execute(delete(models.NotificationLog).where(
            models.NotificationLog.user_id == user.id, models.NotificationLog.local_date == today,
            models.NotificationLog.kind.in_(kinds)))
    db.commit()
    return _out(st)


@router.get("/timezones")
def timezones(user: models.User = Depends(current_user)):
    return all_timezones()


# --------------------------------------------------------------------------- #
# Push-подписки
# --------------------------------------------------------------------------- #
class SubKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: SubKeys

    @field_validator("endpoint")
    @classmethod
    def _https(cls, v):
        if not v.startswith("https://"):
            raise ValueError("endpoint должен быть https")
        return v


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


@router.get("/push/config")
def push_config(user: models.User = Depends(current_user)):
    return {"public_key": settings.vapid_public_key, "configured": bool(settings.vapid_private_key)}


@router.post("/push/subscriptions")
def subscribe(body: SubscriptionIn, request: Request, db: Session = Depends(get_db),
              user: models.User = Depends(current_user)):
    sub = db.scalar(select(models.PushSubscription)
                    .where(models.PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = models.PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    # Если на устройстве вошли под другим пользователем — подписка переходит к нему.
    sub.user_id = user.id
    sub.p256dh = body.keys.p256dh
    sub.auth = body.keys.auth
    sub.user_agent = (request.headers.get("user-agent") or "")[:500]
    sub.last_ok_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/push/unsubscribe")
def unsubscribe(body: EndpointIn, db: Session = Depends(get_db),
                user: models.User = Depends(current_user)):
    sub = db.scalar(select(models.PushSubscription).where(
        models.PushSubscription.endpoint == body.endpoint,
        models.PushSubscription.user_id == user.id))
    if sub:
        db.delete(sub)
        db.commit()
    return {"ok": True}


@router.post("/push/status")
def push_status(body: EndpointIn, db: Session = Depends(get_db),
                user: models.User = Depends(current_user)):
    subs = list(db.scalars(select(models.PushSubscription)
                           .where(models.PushSubscription.user_id == user.id)))
    return {
        "devices": len(subs),
        "this_device": any(s.endpoint == body.endpoint for s in subs),
    }


@router.post("/push/test")
def push_test(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    if not settings.vapid_private_key:
        raise HTTPException(status_code=503, detail="На сервере не настроены ключи VAPID")
    stamp = utcnow().strftime("%H%M%S")
    payload = push.make_payload("Проверка", "Тестовое уведомление: всё работает",
                                push.screen_url("/"), f"test {stamp}", "test")
    r = push.send_to_user(db, user.id, payload)
    return {"sent": r.sent, "failed": r.failed, "removed": r.removed}


# --------------------------------------------------------------------------- #
# Экран по недавнему уведомлению
# --------------------------------------------------------------------------- #
# iOS не сообщает приложению, что его открыли тапом по уведомлению. Поэтому
# приложение при каждом появлении на экране спрашивает сервер: было ли недавно
# уведомление, на которое ещё не отреагировали, — и открывает нужный экран.
PENDING_WINDOW_MIN = 60
PENDING_SCREENS = {"morning": "/morning", "morning_repeat": "/morning",
                   "evening": "/evening", "evening_repeat": "/evening"}


@router.get("/notifications/pending")
def pending_notification(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    since = utcnow() - timedelta(minutes=PENDING_WINDOW_MIN)
    entry = db.scalar(select(models.NotificationLog).where(
        models.NotificationLog.user_id == user.id,
        models.NotificationLog.kind.in_(PENDING_SCREENS),
        models.NotificationLog.status == "sent",
        models.NotificationLog.opened_at.is_(None),
        models.NotificationLog.sent_at >= since,
    ).order_by(models.NotificationLog.sent_at.desc()).limit(1))
    if entry is None:
        return {"pending": None}
    done = morning_done if entry.kind.startswith("morning") else evening_done
    if done(db, user.id, entry.local_date):
        return {"pending": None}
    return {"pending": {"id": entry.id, "kind": entry.kind,
                        "hash": f"#{PENDING_SCREENS[entry.kind]}?d={entry.local_date.isoformat()}"}}


@router.post("/notifications/{log_id}/opened")
def notification_opened(log_id: int, db: Session = Depends(get_db),
                        user: models.User = Depends(current_user)):
    entry = db.get(models.NotificationLog, log_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Не найдено")
    # Закрываем и это, и более ранние уведомления того же дня — второй раз не перебрасываем.
    db.execute(update(models.NotificationLog).where(
        models.NotificationLog.user_id == user.id,
        models.NotificationLog.local_date == entry.local_date,
        models.NotificationLog.opened_at.is_(None)).values(opened_at=utcnow()))
    db.commit()
    return {"ok": True}
