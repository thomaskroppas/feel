"""Эмоции, отметки, дни, дневник, метки."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import current_user
from ..services import days as days_svc
from ..services.emotions import quadrants
from ..timeutil import local_date_of, to_local, to_utc_naive, utcnow

router = APIRouter(prefix="/api", tags=["journal"])

Quadrant = Literal["red", "yellow", "blue", "green"]
TagGroup = Literal["with", "where", "doing"]


def _settings(db: Session, user: models.User) -> models.UserSettings:
    return db.get(models.UserSettings, user.id)


def _tz(db: Session, user: models.User) -> str:
    return _settings(db, user).timezone


def _today(db: Session, user: models.User) -> date:
    return local_date_of(utcnow(), _tz(db, user))


# --------------------------------------------------------------------------- #
# Справочник эмоций
# --------------------------------------------------------------------------- #
@router.get("/emotions")
def list_emotions(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.scalars(select(models.Emotion).order_by(
        models.Emotion.energy.desc(), models.Emotion.pleasantness))
    return {
        "quadrants": quadrants(),
        "emotions": [{
            "id": e.id, "name": e.name, "quadrant": e.quadrant, "energy": e.energy,
            "pleasantness": e.pleasantness, "intensity": e.intensity,
            "description": e.description, "hidden": e.hidden,
        } for e in rows],
    }


# --------------------------------------------------------------------------- #
# Отметки
# --------------------------------------------------------------------------- #
class CheckinIn(BaseModel):
    emotion_id: str = Field(max_length=64)
    occurred_at: Optional[datetime] = None
    source: Literal["manual", "evening", "notification"] = "manual"
    note: Optional[str] = Field(default=None, max_length=10000)
    tag_ids: List[int] = Field(default_factory=list, max_length=100)


class CheckinPatch(BaseModel):
    emotion_id: Optional[str] = Field(default=None, max_length=64)
    occurred_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=10000)
    tag_ids: Optional[List[int]] = Field(default=None, max_length=100)


def _own_checkin(db: Session, user: models.User, checkin_id: int) -> models.Checkin:
    c = db.get(models.Checkin, checkin_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return c


def _own_tags(db: Session, user: models.User, tag_ids: List[int]) -> List[models.Tag]:
    ids = set(tag_ids)
    if not ids:
        return []
    tags = list(db.scalars(select(models.Tag).where(
        models.Tag.id.in_(ids), models.Tag.user_id == user.id)))
    if len(tags) != len(ids):
        raise HTTPException(status_code=422, detail="Неизвестная метка")
    return tags


def _emotion(db: Session, emotion_id: str, allow_hidden: bool = False) -> models.Emotion:
    e = db.get(models.Emotion, emotion_id)
    if e is None or (e.hidden and not allow_hidden):
        raise HTTPException(status_code=422, detail="Неизвестная эмоция")
    return e


def _occurred(value: Optional[datetime], tz_name: str) -> datetime:
    if value is None:
        return utcnow()
    at = to_utc_naive(value, tz_name)
    if at > utcnow() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Время записи не может быть в будущем")
    return at


@router.post("/checkins", status_code=201)
def create_checkin(body: CheckinIn, db: Session = Depends(get_db),
                   user: models.User = Depends(current_user)):
    tz_name = _tz(db, user)
    _emotion(db, body.emotion_id)
    at = _occurred(body.occurred_at, tz_name)
    c = models.Checkin(
        user_id=user.id, emotion_id=body.emotion_id, occurred_at=at,
        local_date=local_date_of(at, tz_name), source=body.source,
        note=(body.note or "").strip() or None,
    )
    c.tags = _own_tags(db, user, body.tag_ids)
    db.add(c)
    db.commit()
    db.refresh(c)
    return days_svc.serialize_checkin(c, tz_name)


@router.get("/checkins/{checkin_id}")
def get_checkin(checkin_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(current_user)):
    return days_svc.serialize_checkin(_own_checkin(db, user, checkin_id), _tz(db, user))


@router.patch("/checkins/{checkin_id}")
def update_checkin(checkin_id: int, body: CheckinPatch, db: Session = Depends(get_db),
                   user: models.User = Depends(current_user)):
    c = _own_checkin(db, user, checkin_id)
    tz_name = _tz(db, user)
    if body.emotion_id is not None and body.emotion_id != c.emotion_id:
        _emotion(db, body.emotion_id)
        c.emotion_id = body.emotion_id
    if body.occurred_at is not None:
        c.occurred_at = _occurred(body.occurred_at, tz_name)
        c.local_date = local_date_of(c.occurred_at, tz_name)
    if body.note is not None:
        c.note = body.note.strip() or None
    if body.tag_ids is not None:
        c.tags = _own_tags(db, user, body.tag_ids)
    c.updated_at = utcnow()
    db.commit()
    db.expire(c)
    return days_svc.serialize_checkin(_own_checkin(db, user, checkin_id), tz_name)


@router.delete("/checkins/{checkin_id}")
def delete_checkin(checkin_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(current_user)):
    c = _own_checkin(db, user, checkin_id)
    db.delete(c)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Дни
# --------------------------------------------------------------------------- #
class DayLogIn(BaseModel):
    plan_status: Optional[Literal["yes", "no"]] = None
    plan_text: Optional[str] = Field(default=None, max_length=10000)
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(default=None, ge=1, le=5)
    sport_type: Optional[str] = Field(default=None, max_length=100)
    sport_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    day_summary: Optional[str] = Field(default=None, max_length=20000)

    @field_validator("sleep_hours")
    @classmethod
    def _half_hours(cls, v):
        if v is not None and round(v * 2) != v * 2:
            raise ValueError("Сон указывается с шагом 0,5 часа")
        return v


def _check_date(d: date, today: date) -> None:
    if d > today + timedelta(days=1):
        raise HTTPException(status_code=422, detail="Нельзя заполнить будущий день")


@router.get("/today")
def today(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    st = _settings(db, user)
    d = local_date_of(utcnow(), st.timezone)
    return {
        "date": d.isoformat(),
        "now_local": to_local(utcnow(), st.timezone).strftime("%Y-%m-%dT%H:%M"),
        "day": days_svc.get_day(db, user, d, st.timezone),
        "week": days_svc.week(db, user.id, d),
    }


@router.get("/days/{d}")
def get_day(d: date, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return days_svc.get_day(db, user, d, _tz(db, user))


@router.put("/days/{d}")
def put_day(d: date, body: DayLogIn, db: Session = Depends(get_db),
            user: models.User = Depends(current_user)):
    tz_name = _tz(db, user)
    _check_date(d, local_date_of(utcnow(), tz_name))
    log = db.get(models.DayLog, (user.id, d))
    if log is None:
        log = models.DayLog(user_id=user.id, local_date=d)
        db.add(log)
    for field, value in body.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
            # Пустой sport_type — «спорта не было»; пустой текст в остальных полях — ничего.
            if not value and field != "sport_type":
                value = None
        setattr(log, field, value)
    if log.plan_text:
        log.plan_remind_at = None
    db.commit()
    return days_svc.get_day(db, user, d, tz_name)


@router.post("/days/{d}/plan-reminder")
def plan_reminder(d: date, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """«Напомнить через 30 минут»."""
    tz_name = _tz(db, user)
    _check_date(d, local_date_of(utcnow(), tz_name))
    log = db.get(models.DayLog, (user.id, d))
    if log is None:
        log = models.DayLog(user_id=user.id, local_date=d, plan_status="no")
        db.add(log)
    log.plan_remind_at = utcnow() + timedelta(minutes=30)
    db.commit()
    return days_svc.get_day(db, user, d, tz_name)


@router.get("/diary")
def diary(before: Optional[date] = None, days: int = Query(default=14, ge=1, le=60),
          quadrant: Optional[Quadrant] = None, tag_id: Optional[int] = None,
          db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """Записи по дням, новые сверху. Фильтр по квадранту и метке."""
    tz_name = _tz(db, user)
    filtered = quadrant is not None or tag_id is not None

    cq = select(models.Checkin.local_date).where(models.Checkin.user_id == user.id)
    if quadrant:
        cq = cq.join(models.Emotion).where(models.Emotion.quadrant == quadrant)
    if tag_id is not None:
        cq = cq.join(models.CheckinTag).where(models.CheckinTag.tag_id == tag_id)
    if before:
        cq = cq.where(models.Checkin.local_date < before)
    dates = set(db.scalars(cq.distinct().order_by(models.Checkin.local_date.desc()).limit(days)))
    if not filtered:
        lq = select(models.DayLog.local_date).where(models.DayLog.user_id == user.id)
        if before:
            lq = lq.where(models.DayLog.local_date < before)
        dates |= set(db.scalars(lq.order_by(models.DayLog.local_date.desc()).limit(days)))
    ordered = sorted(dates, reverse=True)[:days]
    if not ordered:
        return {"days": [], "next_before": None}

    start, end = ordered[-1], ordered[0]
    all_checkins = days_svc.checkins_between(db, user.id, start, end)
    logs = days_svc.day_logs_between(db, user.id, start, end)
    by_day: Dict[date, list] = {}
    for c in all_checkins:
        by_day.setdefault(c.local_date, []).append(c)

    out = []
    for d in ordered:
        items = by_day.get(d, [])
        payload = days_svc.day_payload(d, items, logs.get(d), tz_name)
        if filtered:
            payload["checkins"] = [
                x for x, c in zip(payload["checkins"], items)
                if (not quadrant or c.emotion.quadrant == quadrant)
                and (tag_id is None or any(t.id == tag_id for t in c.tags))
            ]
        payload["checkins"].reverse()  # новые сверху
        out.append(payload)
    return {"days": out, "next_before": ordered[-1].isoformat() if len(ordered) == days else None}


# --------------------------------------------------------------------------- #
# Метки
# --------------------------------------------------------------------------- #
class TagIn(BaseModel):
    group: TagGroup
    name: str = Field(min_length=1, max_length=60)


class TagPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    hidden: Optional[bool] = None


class TagOrder(BaseModel):
    group: TagGroup
    ids: List[int] = Field(max_length=500)


def _tag_out(t: models.Tag) -> dict:
    return {"id": t.id, "group": t.group, "name": t.name, "sort": t.sort, "hidden": t.hidden}


def _own_tag(db: Session, user: models.User, tag_id: int) -> models.Tag:
    t = db.get(models.Tag, tag_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="Метка не найдена")
    return t


@router.get("/tags")
def list_tags(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.scalars(select(models.Tag).where(models.Tag.user_id == user.id)
                      .order_by(models.Tag.group, models.Tag.sort, models.Tag.id))
    return [_tag_out(t) for t in rows]


@router.post("/tags", status_code=201)
def create_tag(body: TagIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Пустое название")
    # SQLite lower() не знает кириллицу, поэтому сравниваем в Python.
    group_tags = db.scalars(select(models.Tag).where(
        models.Tag.user_id == user.id, models.Tag.group == body.group))
    same = next((t for t in group_tags if t.name.casefold() == name.casefold()), None)
    if same:
        same.hidden = False
        db.commit()
        return _tag_out(same)
    last = db.scalar(select(func.max(models.Tag.sort)).where(
        models.Tag.user_id == user.id, models.Tag.group == body.group))
    t = models.Tag(user_id=user.id, group=body.group, name=name, sort=(last or 0) + 1)
    db.add(t)
    db.commit()
    return _tag_out(t)


@router.patch("/tags/{tag_id}")
def update_tag(tag_id: int, body: TagPatch, db: Session = Depends(get_db),
               user: models.User = Depends(current_user)):
    t = _own_tag(db, user, tag_id)
    if body.name is not None:
        name = " ".join(body.name.split())
        if not name:
            raise HTTPException(status_code=422, detail="Пустое название")
        t.name = name
    if body.hidden is not None:
        t.hidden = body.hidden
    db.commit()
    return _tag_out(t)


@router.put("/tags/order")
def reorder_tags(body: TagOrder, db: Session = Depends(get_db),
                 user: models.User = Depends(current_user)):
    tags = {t.id: t for t in db.scalars(select(models.Tag).where(
        models.Tag.user_id == user.id, models.Tag.group == body.group))}
    if set(body.ids) != set(tags):
        raise HTTPException(status_code=422, detail="Список меток не совпадает")
    for i, tag_id in enumerate(body.ids):
        tags[tag_id].sort = i
    db.commit()
    return [_tag_out(tags[i]) for i in body.ids]


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """Удалить можно только неиспользованную метку; использованную — скрыть."""
    t = _own_tag(db, user, tag_id)
    used = db.scalar(select(models.CheckinTag.checkin_id).where(models.CheckinTag.tag_id == t.id).limit(1))
    if used is not None:
        raise HTTPException(status_code=409, detail="Метка уже есть в записях — её можно только скрыть")
    db.execute(delete(models.Tag).where(models.Tag.id == t.id))
    db.commit()
    return {"ok": True}
