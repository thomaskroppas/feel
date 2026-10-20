import json
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app import models
from app.services.notify import run_due

D = date(2026, 10, 20)


def utc(h, m=0, day=20):
    return datetime(2026, 10, day, h, m)


@pytest.fixture
def user(make_user, db):
    u = make_user("a@example.com", timezone="Europe/Moscow")  # UTC+3
    db.add(models.PushSubscription(user_id=u.id, endpoint="https://push.example/1", p256dh="k", auth="a"))
    db.commit()
    return u


def kinds(results):
    return [(r.kind, r.local_date.isoformat(), r.status) for r in results]


def test_morning_sent_on_time_once(user, db, fake_push):
    assert run_due(db, utc(5, 29)) == []  # 08:29 по Москве
    res = run_due(db, utc(5, 32))
    assert kinds(res) == [("morning", "2026-10-20", "sent")]
    payload = json.loads(fake_push.sent[0][1])
    assert payload["url"] == "https://feel.example/#/morning?d=2026-10-20"
    assert payload["tag"] == "morning 2026-10-20 https://feel.example/#/morning?d=2026-10-20"
    assert payload["body"].startswith("Ты составил план")
    assert run_due(db, utc(5, 37)) == []  # дублей нет
    assert len(fake_push.sent) == 1


def test_late_more_than_two_hours_not_sent(user, db, fake_push):
    assert run_due(db, utc(7, 31)) == []  # 10:31 по Москве, опоздание > 2 ч
    assert fake_push.sent == []


def test_not_sent_if_morning_done(user, db, fake_push):
    db.add(models.DayLog(user_id=user.id, local_date=D, plan_status="yes"))
    db.commit()
    assert run_due(db, utc(5, 32)) == []
    assert run_due(db, utc(6, 35)) == []


def test_repeat_after_60_minutes_once_with_same_tag(user, db, fake_push):
    run_due(db, utc(5, 30))
    assert run_due(db, utc(6, 25)) == []
    res = run_due(db, utc(6, 30))
    assert kinds(res) == [("morning_repeat", "2026-10-20", "sent")]
    first, second = (json.loads(x[1]) for x in fake_push.sent)
    assert first["tag"] == second["tag"]  # повтор заменяет прежнее уведомление
    assert run_due(db, utc(6, 35)) == []
    assert run_due(db, utc(7, 40)) == []


def test_no_repeat_if_done_after_first(user, db, fake_push):
    run_due(db, utc(5, 30))
    db.add(models.DayLog(user_id=user.id, local_date=D, plan_status="no"))
    db.commit()
    assert run_due(db, utc(6, 35)) == []


def test_repeat_disabled(user, db, fake_push):
    st = db.get(models.UserSettings, user.id)
    st.repeat_enabled = False
    db.commit()
    run_due(db, utc(5, 30))
    assert run_due(db, utc(6, 35)) == []


def test_repeat_custom_delay(user, db, fake_push):
    st = db.get(models.UserSettings, user.id)
    st.repeat_after_min = 30
    db.commit()
    run_due(db, utc(5, 30))
    assert kinds(run_due(db, utc(6, 0))) == [("morning_repeat", "2026-10-20", "sent")]


def test_disabled_kind_not_sent(user, db, fake_push):
    st = db.get(models.UserSettings, user.id)
    st.morning_enabled = False
    db.commit()
    assert run_due(db, utc(5, 32)) == []


def test_evening_skipped_if_evening_checkin(user, db, fake_push):
    db.add(models.Checkin(user_id=user.id, emotion_id="pokoy", occurred_at=utc(17, 0),
                          local_date=D, source="evening"))
    db.commit()
    assert run_due(db, utc(18, 32)) == []


def test_manual_checkin_does_not_cancel_evening(user, db, fake_push):
    db.add(models.Checkin(user_id=user.id, emotion_id="pokoy", occurred_at=utc(17, 0),
                          local_date=D, source="manual"))
    db.commit()
    res = run_due(db, utc(18, 32))
    assert kinds(res) == [("evening", "2026-10-20", "sent")]
    assert json.loads(fake_push.sent[0][1])["url"].endswith("/#/evening?d=2026-10-20")


def test_evening_after_local_midnight_belongs_to_previous_day(user, db, fake_push):
    st = db.get(models.UserSettings, user.id)
    st.evening_time = "23:55"
    st.morning_enabled = False
    db.commit()
    res = run_due(db, utc(21, 2))  # 00:02 21 октября по Москве
    assert kinds(res) == [("evening", "2026-10-20", "sent")]


def test_gone_subscription_removed(user, db, fake_push):
    db.add(models.PushSubscription(user_id=user.id, endpoint="https://push.example/2", p256dh="k", auth="a"))
    db.commit()
    fake_push.gone.add("https://push.example/1")
    res = run_due(db, utc(5, 32))
    assert kinds(res) == [("morning", "2026-10-20", "sent")]
    endpoints = db.scalars(select(models.PushSubscription.endpoint)).all()
    assert endpoints == ["https://push.example/2"]


def test_all_devices_receive(user, db, fake_push):
    db.add(models.PushSubscription(user_id=user.id, endpoint="https://push.example/2", p256dh="k", auth="a"))
    db.commit()
    run_due(db, utc(5, 32))
    assert sorted(e for e, _ in fake_push.sent) == ["https://push.example/1", "https://push.example/2"]


def test_no_subscriptions_logged_and_no_repeat(make_user, db, fake_push):
    make_user("lonely@example.com")
    assert kinds(run_due(db, utc(5, 32))) == [("morning", "2026-10-20", "no_subscriptions")]
    assert run_due(db, utc(6, 35)) == []


def test_each_user_own_timezone(user, make_user, db, fake_push):
    vl = make_user("vl@example.com", timezone="Asia/Vladivostok")  # UTC+10
    db.add(models.PushSubscription(user_id=vl.id, endpoint="https://push.example/vl", p256dh="k", auth="a"))
    db.commit()
    res = run_due(db, datetime(2026, 10, 19, 22, 31))  # 08:31 20-го во Владивостоке
    assert [(r.user_id, r.kind) for r in res] == [(vl.id, "morning")]


def test_plan_reminder_sent_once(user, db, fake_push):
    db.add(models.DayLog(user_id=user.id, local_date=D, plan_status="no", plan_remind_at=utc(6, 0)))
    db.commit()
    assert [r.kind for r in run_due(db, utc(5, 59)) if r.kind == "plan"] == []
    res = [r for r in run_due(db, utc(6, 2)) if r.kind == "plan"]
    assert [(r.kind, r.status) for r in res] == [("plan", "sent")]
    assert [r for r in run_due(db, utc(6, 7)) if r.kind == "plan"] == []
    assert db.get(models.DayLog, (user.id, D)).plan_remind_at is None


def test_plan_reminder_skipped_if_plan_written(user, db, fake_push):
    db.add(models.DayLog(user_id=user.id, local_date=D, plan_status="no", plan_text="готово",
                         plan_remind_at=utc(6, 0)))
    db.commit()
    assert [r for r in run_due(db, utc(6, 2)) if r.kind == "plan"] == []


def test_push_test_endpoint(client_for, fake_push):
    a = client_for("t@example.com")
    a.post("/api/push/subscriptions", {"endpoint": "https://push.example/t", "keys": {"p256dh": "k", "auth": "x"}})
    assert a.post("/api/push/status", {"endpoint": "https://push.example/t"}).json() == {"devices": 1, "this_device": True}
    assert a.post("/api/push/test").json()["sent"] == 1
    payload = json.loads(fake_push.sent[0][1])
    assert payload["url"] == "https://feel.example/#/"


def test_subscription_moves_to_new_owner(client_for, db):
    a = client_for("a1@example.com")
    b = client_for("b1@example.com")
    sub = {"endpoint": "https://push.example/shared", "keys": {"p256dh": "k", "auth": "x"}}
    a.post("/api/push/subscriptions", sub)
    b.post("/api/push/subscriptions", sub)
    assert a.post("/api/push/status", {"endpoint": sub["endpoint"]}).json()["devices"] == 0
    assert b.post("/api/push/status", {"endpoint": sub["endpoint"]}).json()["devices"] == 1


def test_cli_send_due_runs(user, fake_push, capsys):
    from app.cli import main
    assert main(["send-due"]) == 0
