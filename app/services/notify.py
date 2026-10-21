"""Рассылка утренних и вечерних уведомлений. Запускается cron раз в минуту.

Правила (ТЗ, раздел «Уведомления»):
- для каждого пользователя считается местное время по его часовому поясу;
- журнал с уникальным ключом «пользователь + вид + местная дата» исключает дубли;
- опоздание больше PUSH_MAX_DELAY_MIN (2 часа) — не отправлять;
- не отправлять, если действие уже сделано; повтор — один раз через N минут.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..timeutil import tz, utcnow
from . import push
from .days import evening_done, morning_done

log = logging.getLogger("feel.notify")

KINDS = {
    "morning": {"screen": "/morning", "done": morning_done},
    "evening": {"screen": "/evening", "done": evening_done},
}
# Название приложения iOS показывает сама («from Feel»), поэтому в заголовке — суть уведомления.
TITLES = {"morning": "Утро", "evening": "Вечер", "plan": "План на день"}


@dataclass
class Sent:
    user_id: int
    kind: str
    local_date: date
    status: str


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _scheduled_utc(d: date, at: time, tz_name: str) -> datetime:
    local = datetime.combine(d, at, tzinfo=tz(tz_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _in_window(now: datetime, due: datetime) -> bool:
    return due <= now <= due + timedelta(minutes=settings.push_max_delay_min)


def _claim(db: Session, user_id: int, kind: str, d: date,
           now: datetime) -> Optional[models.NotificationLog]:
    """Записывает в журнал до отправки. Уникальный ключ не даст отправить дважды."""
    entry = models.NotificationLog(user_id=user_id, kind=kind, local_date=d, sent_at=now,
                                   status="sending")
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return entry


def _log_entry(db: Session, user_id: int, kind: str, d: date) -> Optional[models.NotificationLog]:
    return db.scalar(select(models.NotificationLog).where(
        models.NotificationLog.user_id == user_id, models.NotificationLog.kind == kind,
        models.NotificationLog.local_date == d))


def _send(db: Session, st: models.UserSettings, kind: str, d: date, log_kind: str,
          now: datetime) -> Optional[Sent]:
    entry = _claim(db, st.user_id, log_kind, d, now)
    if entry is None:
        return None
    text = st.morning_text if kind == "morning" else st.evening_text
    url = push.screen_url(f"{KINDS[kind]['screen']}?d={d.isoformat()}")
    # Повтор идёт с тем же tag, что и основное, и заменяет его на экране.
    payload = push.make_payload(TITLES[kind], text, url, f"{kind} {d.isoformat()}", log_kind)
    result = push.send_to_user(db, st.user_id, payload)
    entry.status = result.status
    db.commit()
    return Sent(st.user_id, log_kind, d, result.status)


def _process_user(db: Session, st: models.UserSettings, now: datetime) -> List[Sent]:
    out: List[Sent] = []
    local_today = now.replace(tzinfo=timezone.utc).astimezone(tz(st.timezone)).date()
    # Вчерашний день тоже: вечер в 23:30 может уйти уже после местной полуночи.
    for d in (local_today - timedelta(days=1), local_today):
        for kind, meta in KINDS.items():
            if not getattr(st, f"{kind}_enabled"):
                continue
            due = _scheduled_utc(d, _parse_hhmm(getattr(st, f"{kind}_time")), st.timezone)
            if now < due:
                continue
            done = None  # считается лениво, только если есть что отправлять

            main = _log_entry(db, st.user_id, kind, d)
            if main is None:
                if _in_window(now, due):
                    done = meta["done"](db, st.user_id, d)
                    if not done:
                        sent = _send(db, st, kind, d, kind, now)
                        if sent:
                            out.append(sent)
                continue

            if not st.repeat_enabled or main.status != "sent":
                continue
            repeat_due = main.sent_at + timedelta(minutes=st.repeat_after_min)
            if not _in_window(now, repeat_due):
                continue
            if _log_entry(db, st.user_id, f"{kind}_repeat", d) is not None:
                continue
            if done is None:
                done = meta["done"](db, st.user_id, d)
            if not done:
                sent = _send(db, st, kind, d, f"{kind}_repeat", now)
                if sent:
                    out.append(sent)
    return out


def _process_plan_reminders(db: Session, now: datetime) -> List[Sent]:
    """«Напомнить через 30 минут» с утреннего экрана."""
    out: List[Sent] = []
    rows = list(db.scalars(select(models.DayLog).where(
        models.DayLog.plan_remind_at.is_not(None), models.DayLog.plan_remind_at <= now)))
    for row in rows:
        due = row.plan_remind_at
        # Забираем напоминание атомарно, чтобы параллельный запуск его не повторил.
        claimed = db.execute(update(models.DayLog).where(
            models.DayLog.user_id == row.user_id, models.DayLog.local_date == row.local_date,
            models.DayLog.plan_remind_at == due).values(plan_remind_at=None)).rowcount
        db.commit()
        if not claimed or not _in_window(now, due):
            continue
        if (row.plan_text or "").strip():
            continue
        d = row.local_date
        url = push.screen_url(f"/morning?d={d.isoformat()}")
        payload = push.make_payload(TITLES["plan"], "Пора выделить 30 минут на план дня", url,
                                    f"plan {d.isoformat()}", "plan")
        result = push.send_to_user(db, row.user_id, payload)
        out.append(Sent(row.user_id, "plan", d, result.status))
    return out


def run_due(db: Session, now: datetime = None) -> List[Sent]:
    now = now or utcnow()
    out: List[Sent] = []
    for st in list(db.scalars(select(models.UserSettings))):
        try:
            out.extend(_process_user(db, st, now))
        except Exception:
            db.rollback()
            log.exception("notify failed for user %s", st.user_id)
    out.extend(_process_plan_reminders(db, now))
    return out
