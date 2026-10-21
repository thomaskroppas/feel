"""Дни и отметки: цвет дня, сериализация, выборки по пользователю."""
from collections import Counter
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..timeutil import iso_utc, to_local
from . import media as media_svc

DAY_LOG_FIELDS = ("plan_status", "plan_text", "sleep_hours", "sleep_quality",
                  "sport_type", "sport_minutes", "day_summary")


def day_quadrant(checkins: Iterable[models.Checkin]) -> Optional[str]:
    """Квадрант вечерней отметки; если её нет — квадрант, которого за день больше всего.

    При равенстве побеждает квадрант более поздней отметки.
    """
    items = sorted(checkins, key=lambda c: c.occurred_at)
    if not items:
        return None
    evening = [c for c in items if c.source == "evening"]
    if evening:
        return evening[-1].emotion.quadrant
    counts = Counter(c.emotion.quadrant for c in items)
    top = max(counts.values())
    for c in reversed(items):
        if counts[c.emotion.quadrant] == top:
            return c.emotion.quadrant
    return None


def serialize_checkin(c: models.Checkin, tz_name: str) -> dict:
    local = to_local(c.occurred_at, tz_name)
    return {
        "id": c.id,
        "emotion_id": c.emotion_id,
        "emotion": {"name": c.emotion.name, "quadrant": c.emotion.quadrant,
                    "energy": c.emotion.energy, "pleasantness": c.emotion.pleasantness},
        "occurred_at": iso_utc(c.occurred_at),
        "local_time": local.strftime("%H:%M"),
        "local_date": c.local_date.isoformat(),
        "source": c.source,
        "note": c.note or "",
        "tags": [{"id": t.id, "group": t.group, "name": t.name} for t in c.tags],
        "media": [media_svc.serialize(m) for m in c.media],
    }


def serialize_day_log(d: Optional[models.DayLog]) -> Optional[dict]:
    if d is None:
        return None
    out = {f: getattr(d, f) for f in DAY_LOG_FIELDS}
    out["plan_remind_at"] = iso_utc(d.plan_remind_at) if d.plan_remind_at else None
    return out


def checkins_between(db: Session, user_id: int, start: date, end: date) -> List[models.Checkin]:
    return list(db.scalars(
        select(models.Checkin)
        .where(models.Checkin.user_id == user_id,
               models.Checkin.local_date >= start, models.Checkin.local_date <= end)
        .order_by(models.Checkin.occurred_at)
    ).unique())


def day_logs_between(db: Session, user_id: int, start: date, end: date) -> Dict[date, models.DayLog]:
    rows = db.scalars(select(models.DayLog).where(
        models.DayLog.user_id == user_id,
        models.DayLog.local_date >= start, models.DayLog.local_date <= end))
    return {r.local_date: r for r in rows}


def day_payload(d: date, checkins: List[models.Checkin], log: Optional[models.DayLog],
                tz_name: str, media: Optional[List[models.Media]] = None) -> dict:
    return {
        "date": d.isoformat(),
        "quadrant": day_quadrant(checkins),
        "day_log": serialize_day_log(log),
        "media": [media_svc.serialize(m) for m in (media or [])],
        "checkins": [serialize_checkin(c, tz_name) for c in checkins],
        "has_evening": any(c.source == "evening" for c in checkins),
    }


def get_day(db: Session, user: models.User, d: date, tz_name: str) -> dict:
    checkins = checkins_between(db, user.id, d, d)
    log = db.get(models.DayLog, (user.id, d))
    return day_payload(d, checkins, log, tz_name, media_svc.day_media(db, user.id, d, d))


def week(db: Session, user_id: int, today: date) -> List[dict]:
    start = today - timedelta(days=6)
    by_day: Dict[date, list] = {}
    for c in checkins_between(db, user_id, start, today):
        by_day.setdefault(c.local_date, []).append(c)
    out = []
    for i in range(7):
        d = start + timedelta(days=i)
        items = by_day.get(d, [])
        out.append({"date": d.isoformat(), "quadrant": day_quadrant(items), "count": len(items)})
    return out


def evening_done(db: Session, user_id: int, d: date) -> bool:
    return db.scalar(select(models.Checkin.id).where(
        models.Checkin.user_id == user_id, models.Checkin.local_date == d,
        models.Checkin.source == "evening").limit(1)) is not None


def morning_done(db: Session, user_id: int, d: date) -> bool:
    log = db.get(models.DayLog, (user_id, d))
    return log is not None and log.plan_status is not None
