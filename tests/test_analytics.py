"""Отчёты на тестовом наборе с заранее посчитанными вручную ответами."""
from datetime import date, datetime, timedelta

import pytest

from app import models
from app.services import analytics
from app.timeutil import to_utc_naive

TODAY = date(2026, 10, 20)
TZ = "Europe/Moscow"
# Приятность / энергия слов из emotions.json:
# radost p11 e9 (yellow), trevoga p4 e10 (red), ustalost p6 e3 (blue), pokoy p9 e2 (green)


@pytest.fixture
def user(make_user):
    return make_user("a@example.com", timezone=TZ)


def add(db, user, eid, d, hm="12:00", source="manual", tags=()):
    at = to_utc_naive(datetime.fromisoformat(f"{d}T{hm}"), TZ)
    c = models.Checkin(user_id=user.id, emotion_id=eid, occurred_at=at, local_date=date.fromisoformat(d),
                       source=source)
    c.tags = list(tags)
    db.add(c)
    db.commit()
    return c


def log(db, user, d, **fields):
    db.add(models.DayLog(user_id=user.id, local_date=date.fromisoformat(d), **fields))
    db.commit()


def run(db, user, period="week", month=None):
    db.expire_all()
    return analytics.compute(db, user, TZ, period, TODAY, month)


def test_top_quadrants_dayparts_dynamics(db, user):
    add(db, user, "radost", "2026-10-20", "08:00")
    add(db, user, "radost", "2026-10-20", "13:00")
    add(db, user, "trevoga", "2026-10-20", "18:00")
    add(db, user, "ustalost", "2026-10-19", "23:30")
    add(db, user, "pokoy", "2026-10-19", "09:00")
    add(db, user, "trevoga", "2026-10-01", "09:00")  # вне недели
    r = run(db, user)

    assert r["start"] == "2026-10-14" and r["end"] == "2026-10-20" and r["total"] == 5
    assert [(e["id"], e["count"]) for e in r["top"]["emotions"]] == [
        ("radost", 2), ("pokoy", 1), ("trevoga", 1), ("ustalost", 1)]
    assert r["top"]["quadrants"] == {"red": 1, "yellow": 2, "blue": 1, "green": 1}

    parts = {p["key"]: p for p in r["dayparts"]}
    assert parts["morning"]["quadrants"] == {"red": 0, "yellow": 1, "blue": 0, "green": 1}
    assert parts["day"]["quadrants"]["yellow"] == 1 and parts["day"]["total"] == 1
    assert parts["evening"]["quadrants"]["red"] == 1
    assert parts["night"]["quadrants"]["blue"] == 1

    days = {d["date"]: d for d in r["dynamics"]["days"]}
    assert len(days) == 7
    assert days["2026-10-20"]["pleasantness"] == 8.67 and days["2026-10-20"]["energy"] == 9.33
    assert days["2026-10-19"]["pleasantness"] == 7.5 and days["2026-10-19"]["energy"] == 2.5
    assert days["2026-10-18"]["pleasantness"] is None
    assert len(r["dynamics"]["points"]) == 5


def test_daypart_boundaries():
    assert [analytics.daypart(h) for h in (4, 5, 11, 12, 16, 17, 22, 23, 0)] == [
        "night", "morning", "morning", "day", "day", "evening", "evening", "night", "night"]


def test_tags_with_and_without(db, user):
    friends = models.Tag(user_id=user.id, group="with", name="Друзья2", sort=99)
    cat = models.Tag(user_id=user.id, group="with", name="Кот", sort=100)
    db.add_all([friends, cat])
    db.commit()
    for i in range(5):
        add(db, user, "radost", f"2026-10-{15 + i}", "10:00", tags=[friends] + ([cat] if i < 2 else []))
        add(db, user, "trevoga", f"2026-10-{15 + i}", "15:00")
    rows = {t["name"]: t for t in run(db, user)["tags"]}
    f = rows["Друзья2"]
    assert f["with"] == {"n": 5, "avg": 11.0} and f["without"] == {"n": 5, "avg": 4.0}
    assert f["diff"] == 7.0
    k = rows["Кот"]
    assert k["with"] == {"n": 2, "avg": None} and k["diff"] is None
    assert run(db, user)["tags"][0]["name"] == "Друзья2"  # сначала значимые, по величине разницы


def test_sleep_and_sport(db, user):
    start = TODAY - timedelta(days=11)
    for i in range(12):
        d = (start + timedelta(days=i)).isoformat()
        if i < 5:      # мало сна, спорта не было, приятность 4
            add(db, user, "trevoga", d)
            log(db, user, d, sleep_hours=5.0, sport_type="")
        elif i < 10:   # 6–8 ч, был спорт, приятность 9
            add(db, user, "pokoy", d)
            log(db, user, d, sleep_hours=7.0 if i < 9 else 8.0, sport_type="Бег", sport_minutes=30)
        else:          # больше 8 ч, спорт не указан, приятность 11
            add(db, user, "radost", d)
            log(db, user, d, sleep_hours=9.0)
    r = run(db, user, "month")
    sleep = {s["key"]: s for s in r["sleep"]}
    assert sleep["lt6"]["n"] == 5 and sleep["lt6"]["avg"] == 4.0
    assert sleep["6to8"]["n"] == 5 and sleep["6to8"]["avg"] == 9.0
    assert sleep["gt8"]["n"] == 2 and sleep["gt8"]["avg"] is None   # мало данных
    assert r["sport"]["yes"] == {"n": 5, "avg": 9.0} and r["sport"]["no"] == {"n": 5, "avg": 4.0}
    assert r["sport"]["diff"] == 5.0


def test_sleep_day_value_is_mean_of_day(db, user):
    for i in range(5):
        d = (TODAY - timedelta(days=i)).isoformat()
        add(db, user, "radost", d, "09:00")   # 11
        add(db, user, "trevoga", d, "19:00")  # 4 → среднее дня 7.5
        log(db, user, d, sleep_hours=4.5)
    assert {s["key"]: s for s in run(db, user)["sleep"]}["lt6"]["avg"] == 7.5


def test_plan_uses_evening_checkin(db, user):
    for i in range(5):
        d = (TODAY - timedelta(days=i)).isoformat()
        add(db, user, "ustalost", d, "08:00")                    # обычная отметка не считается
        add(db, user, "radost", d, "21:00", source="evening")    # 11
        log(db, user, d, plan_status="yes")
    for i in range(5, 10):
        d = (TODAY - timedelta(days=i)).isoformat()
        add(db, user, "trevoga", d, "21:00", source="evening")   # 4
        log(db, user, d, plan_status="no")
    log(db, user, (TODAY - timedelta(days=12)).isoformat(), plan_status="yes")  # без вечера — не в счёт
    r = run(db, user, "month")
    assert r["plan"]["yes"] == {"n": 5, "avg": 11.0}
    assert r["plan"]["no"] == {"n": 5, "avg": 4.0}
    assert r["plan"]["diff"] == 7.0


def test_plan_not_enough(db, user):
    add(db, user, "radost", "2026-10-20", "21:00", source="evening")
    log(db, user, "2026-10-20", plan_status="yes")
    r = run(db, user)
    assert r["plan"]["yes"] == {"n": 1, "avg": None} and r["plan"]["diff"] is None


def test_calendar_month(db, user):
    add(db, user, "radost", "2026-10-20", "09:00")
    add(db, user, "ustalost", "2026-10-20", "21:00", source="evening")
    add(db, user, "trevoga", "2026-09-30", "09:00")
    cal = run(db, user)["calendar"]
    assert cal["month"] == "2026-10" and len(cal["days"]) == 31
    days = {d["date"]: d for d in cal["days"]}
    assert days["2026-10-20"]["quadrant"] == "blue" and days["2026-10-20"]["count"] == 2
    assert days["2026-10-01"]["quadrant"] is None
    sep = run(db, user, month=date(2026, 9, 1))["calendar"]
    assert len(sep["days"]) == 30 and sep["days"][-1]["quadrant"] == "red"


def test_period_all_starts_from_first_record(db, user):
    add(db, user, "radost", "2025-01-05")
    r = run(db, user, "all")
    assert r["start"] == "2025-01-05" and r["total"] == 1


def test_analytics_endpoint_isolated(client_for):
    a = client_for("a2@example.com")
    b = client_for("b2@example.com")
    a.post("/api/checkins", {"emotion_id": "radost"})
    assert a.get("/api/analytics?period=week").json()["total"] == 1
    assert b.get("/api/analytics?period=week").json()["total"] == 0
    assert a.get("/api/analytics?period=decade").status_code == 422
    assert a.get("/api/analytics?period=month&month=2026-09").json()["calendar"]["month"] == "2026-09"
