"""Отчёты аналитики. Всё считается на сервере по записям пользователя за период.

Связи (метки, сон и спорт, план) показываются только при MIN_GROUP и более
записях в каждой группе, иначе среднее не отдаётся — интерфейс пишет «мало данных».
"""
import calendar as cal
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..timeutil import to_local
from .days import checkins_between, day_logs_between, day_quadrant

PERIOD_DAYS = {"week": 7, "month": 30, "3months": 90, "year": 365}
PERIODS = tuple(PERIOD_DAYS) + ("all",)
MIN_GROUP = 5
QUADRANTS = ("red", "yellow", "blue", "green")
# Время суток по местному часу записи.
DAYPARTS = (("morning", "Утро", 5, 12), ("day", "День", 12, 17),
            ("evening", "Вечер", 17, 23), ("night", "Ночь", 23, 5))
SLEEP_GROUPS = (("lt6", "меньше 6 ч"), ("6to8", "6–8 ч"), ("gt8", "больше 8 ч"))


def _r(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x, 2)


def _avg(values: List[float]) -> Optional[float]:
    return _r(mean(values)) if values else None


def _group(values: List[float]) -> dict:
    """Группа для сравнения: среднее отдаётся, только если записей достаточно."""
    return {"n": len(values), "avg": _avg(values) if len(values) >= MIN_GROUP else None}


def _diff(a: dict, b: dict) -> Optional[float]:
    if a["avg"] is None or b["avg"] is None:
        return None
    return _r(a["avg"] - b["avg"])


def period_bounds(db: Session, user_id: int, period: str, today: date) -> tuple:
    if period == "all":
        first = db.scalar(select(func.min(models.Checkin.local_date))
                          .where(models.Checkin.user_id == user_id))
        first_log = db.scalar(select(func.min(models.DayLog.local_date))
                              .where(models.DayLog.user_id == user_id))
        candidates = [d for d in (first, first_log) if d]
        return (min(candidates) if candidates else today), today
    return today - timedelta(days=PERIOD_DAYS[period] - 1), today


def daypart(hour: int) -> str:
    for key, _label, start, end in DAYPARTS:
        if start < end and start <= hour < end:
            return key
    return "night"


def sleep_group(hours: float) -> str:
    if hours < 6:
        return "lt6"
    if hours <= 8:
        return "6to8"
    return "gt8"


def calendar_month(db: Session, user_id: int, month: date) -> dict:
    first = month.replace(day=1)
    last = first.replace(day=cal.monthrange(first.year, first.month)[1])
    by_day: Dict[date, list] = defaultdict(list)
    for c in checkins_between(db, user_id, first, last):
        by_day[c.local_date].append(c)
    return {
        "month": first.strftime("%Y-%m"),
        "days": [{"date": (first + timedelta(days=i)).isoformat(),
                  "quadrant": day_quadrant(by_day.get(first + timedelta(days=i), [])),
                  "count": len(by_day.get(first + timedelta(days=i), []))}
                 for i in range(last.day)],
    }


def compute(db: Session, user: models.User, tz_name: str, period: str, today: date,
            month: Optional[date] = None) -> dict:
    start, end = period_bounds(db, user.id, period, today)
    checkins = checkins_between(db, user.id, start, end)
    logs = day_logs_between(db, user.id, start, end)
    by_day: Dict[date, List[models.Checkin]] = defaultdict(list)
    for c in checkins:
        by_day[c.local_date].append(c)

    # ---------- Динамика ----------
    days = []
    d = start
    while d <= end:
        items = by_day.get(d, [])
        days.append({"date": d.isoformat(),
                     "pleasantness": _avg([c.emotion.pleasantness for c in items]),
                     "energy": _avg([c.emotion.energy for c in items])})
        d += timedelta(days=1)
    points = [{"date": c.local_date.isoformat(),
               "time": to_local(c.occurred_at, tz_name).strftime("%H:%M"),
               "pleasantness": c.emotion.pleasantness, "energy": c.emotion.energy,
               "quadrant": c.emotion.quadrant, "name": c.emotion.name} for c in checkins]

    # ---------- Частые эмоции ----------
    counts = Counter(c.emotion_id for c in checkins)
    names = {c.emotion_id: c.emotion for c in checkins}
    top = sorted(counts.items(), key=lambda kv: (-kv[1], names[kv[0]].name))[:10]
    quad_counts = Counter(c.emotion.quadrant for c in checkins)

    # ---------- Время суток ----------
    parts = {key: Counter() for key, *_ in DAYPARTS}
    for c in checkins:
        parts[daypart(to_local(c.occurred_at, tz_name).hour)][c.emotion.quadrant] += 1

    # ---------- Метки ----------
    tag_rows = []
    tags_used = {t.id: t for c in checkins for t in c.tags}
    for tag_id, tag in tags_used.items():
        with_ = [c.emotion.pleasantness for c in checkins if any(t.id == tag_id for t in c.tags)]
        without = [c.emotion.pleasantness for c in checkins if all(t.id != tag_id for t in c.tags)]
        g_with, g_without = _group(with_), _group(without)
        tag_rows.append({"id": tag.id, "group": tag.group, "name": tag.name,
                         "with": g_with, "without": g_without, "diff": _diff(g_with, g_without)})
    tag_rows.sort(key=lambda r: (r["diff"] is None, -abs(r["diff"] or 0), -r["with"]["n"], r["name"]))

    # ---------- Сон и спорт (по средней приятности дня) ----------
    day_p = {d: mean(c.emotion.pleasantness for c in items) for d, items in by_day.items()}
    sleep_vals: Dict[str, list] = {k: [] for k, _ in SLEEP_GROUPS}
    sport_vals = {"yes": [], "no": []}
    for d, log in logs.items():
        if d not in day_p:
            continue
        if log.sleep_hours is not None:
            sleep_vals[sleep_group(log.sleep_hours)].append(day_p[d])
        if log.sport_type is not None:
            sport_vals["yes" if log.sport_type.strip() else "no"].append(day_p[d])
    sport = {k: _group(v) for k, v in sport_vals.items()}

    # ---------- План (приятность вечерней отметки) ----------
    plan_vals = {"yes": [], "no": []}
    for d, log in logs.items():
        evening = [c for c in by_day.get(d, []) if c.source == "evening"]
        if log.plan_status in plan_vals and evening:
            plan_vals[log.plan_status].append(evening[-1].emotion.pleasantness)
    plan = {k: _group(v) for k, v in plan_vals.items()}

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": len(checkins),
        "min_group": MIN_GROUP,
        "calendar": calendar_month(db, user.id, month or today),
        "dynamics": {"days": days, "points": points},
        "top": {
            "emotions": [{"id": eid, "name": names[eid].name, "quadrant": names[eid].quadrant,
                          "count": n} for eid, n in top],
            "quadrants": {q: quad_counts.get(q, 0) for q in QUADRANTS},
        },
        "dayparts": [{"key": key, "label": label, "total": sum(parts[key].values()),
                      "quadrants": {q: parts[key].get(q, 0) for q in QUADRANTS}}
                     for key, label, *_ in DAYPARTS],
        "tags": tag_rows,
        "sleep": [{"key": k, "label": label, **_group(sleep_vals[k])} for k, label in SLEEP_GROUPS],
        "sport": {**sport, "diff": _diff(sport["yes"], sport["no"])},
        "plan": {**plan, "diff": _diff(plan["yes"], plan["no"])},
    }
