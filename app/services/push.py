"""Отправка Web Push (VAPID) на все подписки пользователя."""
import json
import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..timeutil import utcnow

log = logging.getLogger("feel.push")

TTL_SECONDS = 2 * 3600
# Заголовок уведомления — название приложения, как у значка на экране «Домой».
APP_NAME = "Feel"


class PushGone(Exception):
    """Сервис доставки ответил 404/410 — подписка больше не действует."""


class PushFailed(Exception):
    pass


def _webpush_transport(sub: models.PushSubscription, data: str) -> None:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint,
                               "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=TTL_SECONDS,
            headers={"Urgency": "high"},
            timeout=15,
        )
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            raise PushGone(str(status)) from e
        raise PushFailed(f"HTTP {status}") from e
    except Exception as e:  # сеть, таймаут
        raise PushFailed(type(e).__name__) from e


# Тесты подменяют транспорт, чтобы не ходить в сеть.
transport: Callable[[models.PushSubscription, str], None] = _webpush_transport


@dataclass
class SendResult:
    sent: int = 0
    failed: int = 0
    removed: int = 0

    @property
    def status(self) -> str:
        if self.sent:
            return "sent"
        if self.failed:
            return "failed"
        return "no_subscriptions"


def screen_url(path: str) -> str:
    """Абсолютный адрес экрана (iOS открывает его по тапу на уведомление)."""
    return f"{settings.public_url}/#{path}"


def make_payload(title: str, body: str, url: str, tag: str, kind: str) -> dict:
    # Адрес дублируется в tag: на iOS data в обработчике нажатия бывает пустым.
    return {"title": title, "body": body, "url": url, "tag": f"{tag} {url}", "kind": kind}


def send_to_user(db: Session, user_id: int, payload: dict) -> SendResult:
    result = SendResult()
    data = json.dumps(payload, ensure_ascii=False)
    subs = list(db.scalars(select(models.PushSubscription)
                           .where(models.PushSubscription.user_id == user_id)))
    for sub in subs:
        try:
            transport(sub, data)
            sub.last_ok_at = utcnow()
            result.sent += 1
        except PushGone:
            db.delete(sub)
            result.removed += 1
        except PushFailed as e:
            log.warning("push failed for subscription %s: %s", sub.id, e)
            result.failed += 1
    db.commit()
    return result
