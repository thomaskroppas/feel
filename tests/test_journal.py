from datetime import datetime, timedelta, timezone

from app.services.users import DEFAULT_TAGS


def test_emotions_144(client_for):
    a = client_for("a@example.com")
    data = a.get("/api/emotions").json()
    assert len(data["emotions"]) == 144
    assert [q["id"] for q in data["quadrants"]] == ["red", "yellow", "blue", "green"]
    cells = {(e["energy"], e["pleasantness"]) for e in data["emotions"]}
    assert len(cells) == 144
    for e in data["emotions"]:
        assert e["description"]
        high = e["energy"] >= 7
        pleasant = e["pleasantness"] >= 7
        expected = {(True, False): "red", (True, True): "yellow",
                    (False, False): "blue", (False, True): "green"}[(high, pleasant)]
        assert e["quadrant"] == expected, e["id"]


def test_default_tags(client_for):
    a = client_for("a@example.com")
    tags = a.get("/api/tags").json()
    for group, names in DEFAULT_TAGS.items():
        assert [t["name"] for t in tags if t["group"] == group] == names


def test_checkin_minimal_and_full(client_for):
    a = client_for("a@example.com")
    r = a.post("/api/checkins", {"emotion_id": "radost"})
    assert r.status_code == 201
    c = r.json()
    assert c["emotion"]["quadrant"] == "yellow" and c["source"] == "manual"

    tags = a.get("/api/tags").json()
    ids = [tags[0]["id"], tags[8]["id"]]
    r = a.post("/api/checkins", {"emotion_id": "trevoga", "note": "  заметка ",
                                 "tag_ids": ids, "occurred_at": "2026-10-19T23:30:00+03:00"})
    c = r.json()
    assert c["note"] == "заметка"
    assert sorted(t["id"] for t in c["tags"]) == sorted(ids)
    assert c["local_date"] == "2026-10-19" and c["local_time"] == "23:30"
    assert c["occurred_at"] == "2026-10-19T20:30:00Z"


def test_local_date_uses_user_timezone(client_for):
    a = client_for("a@example.com", timezone="Asia/Vladivostok")
    # 20:30 UTC — в Москве ещё 19-е, во Владивостоке уже 20-е.
    c = a.post("/api/checkins", {"emotion_id": "radost", "occurred_at": "2026-10-19T20:30:00Z"}).json()
    assert c["local_date"] == "2026-10-20" and c["local_time"] == "06:30"


def test_naive_time_is_local(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost", "occurred_at": "2026-10-19T10:00"}).json()
    assert c["occurred_at"] == "2026-10-19T07:00:00Z"


def test_future_checkin_rejected(client_for):
    a = client_for("a@example.com")
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert a.post("/api/checkins", {"emotion_id": "radost", "occurred_at": future}).status_code == 422


def test_unknown_emotion(client_for):
    a = client_for("a@example.com")
    assert a.post("/api/checkins", {"emotion_id": "nope"}).status_code == 422


def test_edit_and_delete_checkin(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    tag = a.get("/api/tags").json()[0]
    r = a.patch(f"/api/checkins/{c['id']}", {"emotion_id": "pokoy", "note": "x", "tag_ids": [tag["id"]]})
    assert r.status_code == 200
    assert r.json()["emotion"]["quadrant"] == "green" and r.json()["tags"][0]["id"] == tag["id"]
    assert a.delete(f"/api/checkins/{c['id']}").status_code == 200
    assert a.get(f"/api/checkins/{c['id']}").status_code == 404


def test_day_log_and_today(client_for):
    a = client_for("a@example.com")
    today = a.get("/api/today").json()
    d = today["date"]
    assert len(today["week"]) == 7 and today["week"][-1]["date"] == d
    r = a.put(f"/api/days/{d}", {"plan_status": "yes", "plan_text": "работа", "sleep_hours": 7.5,
                                 "sleep_quality": 4})
    assert r.status_code == 200
    assert r.json()["day_log"]["plan_status"] == "yes"
    # Частичное обновление не стирает остальные поля.
    r = a.put(f"/api/days/{d}", {"sport_type": "", "day_summary": "хорошо"})
    log = r.json()["day_log"]
    assert log["plan_text"] == "работа" and log["sport_type"] == "" and log["day_summary"] == "хорошо"
    assert a.put(f"/api/days/{d}", {"sleep_hours": 7.3}).status_code == 422
    assert a.put(f"/api/days/{d}", {"sleep_quality": 6}).status_code == 422


def test_plan_reminder(client_for):
    a = client_for("a@example.com")
    d = a.get("/api/today").json()["date"]
    r = a.post(f"/api/days/{d}/plan-reminder")
    assert r.json()["day_log"]["plan_remind_at"] is not None
    assert r.json()["day_log"]["plan_status"] == "no"


def test_day_color_rules(client_for):
    a = client_for("a@example.com")
    d = "2026-10-18"
    for eid, t in [("radost", "09:00"), ("vesele", "10:00"), ("trevoga", "11:00")]:
        a.post("/api/checkins", {"emotion_id": eid, "occurred_at": f"{d}T{t}"})
    assert a.get(f"/api/days/{d}").json()["quadrant"] == "yellow"  # больше всего жёлтых
    a.post("/api/checkins", {"emotion_id": "ustalost", "occurred_at": f"{d}T08:00", "source": "evening"})
    assert a.get(f"/api/days/{d}").json()["quadrant"] == "blue"  # вечерняя отметка главнее


def test_day_color_tie_goes_to_later(client_for):
    a = client_for("a@example.com")
    d = "2026-10-18"
    a.post("/api/checkins", {"emotion_id": "radost", "occurred_at": f"{d}T09:00"})
    a.post("/api/checkins", {"emotion_id": "trevoga", "occurred_at": f"{d}T10:00"})
    assert a.get(f"/api/days/{d}").json()["quadrant"] == "red"


def test_diary_order_filters_and_paging(client_for):
    a = client_for("a@example.com")
    tag = a.get("/api/tags").json()[0]
    a.post("/api/checkins", {"emotion_id": "radost", "occurred_at": "2026-10-10T09:00", "tag_ids": [tag["id"]]})
    a.post("/api/checkins", {"emotion_id": "trevoga", "occurred_at": "2026-10-10T12:00"})
    a.post("/api/checkins", {"emotion_id": "pokoy", "occurred_at": "2026-10-12T09:00"})
    a.put("/api/days/2026-10-11", {"plan_status": "no"})

    days = a.get("/api/diary").json()["days"]
    assert [d["date"] for d in days] == ["2026-10-12", "2026-10-11", "2026-10-10"]
    assert [c["emotion_id"] for c in days[2]["checkins"]] == ["trevoga", "radost"]

    days = a.get("/api/diary?quadrant=yellow").json()["days"]
    assert [d["date"] for d in days] == ["2026-10-10"]
    assert [c["emotion_id"] for c in days[0]["checkins"]] == ["radost"]

    days = a.get(f"/api/diary?tag_id={tag['id']}").json()["days"]
    assert [c["emotion_id"] for d in days for c in d["checkins"]] == ["radost"]

    page = a.get("/api/diary?days=2").json()
    assert [d["date"] for d in page["days"]] == ["2026-10-12", "2026-10-11"]
    page2 = a.get(f"/api/diary?days=2&before={page['next_before']}").json()
    assert [d["date"] for d in page2["days"]] == ["2026-10-10"] and page2["next_before"] is None


def test_tags_crud(client_for):
    a = client_for("a@example.com")
    t = a.post("/api/tags", {"group": "with", "name": "  Кот  "}).json()
    assert t["name"] == "Кот"
    again = a.post("/api/tags", {"group": "with", "name": "кот"}).json()
    assert again["id"] == t["id"]
    a.patch(f"/api/tags/{t['id']}", {"name": "Кошка", "hidden": True})
    tags = a.get("/api/tags").json()
    me = next(x for x in tags if x["id"] == t["id"])
    assert me["name"] == "Кошка" and me["hidden"]
    ids = [x["id"] for x in tags if x["group"] == "with"][::-1]
    assert a.put("/api/tags/order", {"group": "with", "ids": ids}).status_code == 200
    assert [x["id"] for x in a.get("/api/tags").json() if x["group"] == "with"] == ids
    assert a.put("/api/tags/order", {"group": "with", "ids": ids[1:]}).status_code == 422


def test_used_tag_cannot_be_deleted(client_for):
    a = client_for("a@example.com")
    tag = a.get("/api/tags").json()[0]
    a.post("/api/checkins", {"emotion_id": "radost", "tag_ids": [tag["id"]]})
    assert a.delete(f"/api/tags/{tag['id']}").status_code == 409
    fresh = a.post("/api/tags", {"group": "where", "name": "Дача"}).json()
    assert a.delete(f"/api/tags/{fresh['id']}").status_code == 200


def test_settings(client_for):
    a = client_for("a@example.com")
    s = a.get("/api/settings").json()
    assert s["morning_time"] == "08:30" and s["evening_time"] == "21:30" and s["repeat_after_min"] == 60
    assert s["morning_text"].startswith("Ты составил план")
    r = a.put("/api/settings", {"morning_time": "07:45", "timezone": "Asia/Yekaterinburg",
                                "repeat_enabled": False})
    assert r.json()["morning_time"] == "07:45" and r.json()["timezone"] == "Asia/Yekaterinburg"
    assert a.put("/api/settings", {"morning_time": "25:00"}).status_code == 422
    assert a.put("/api/settings", {"timezone": "Mars/Olympus"}).status_code == 422
    assert a.put("/api/settings", {"evening_text": "   "}).status_code == 422


def test_wipe(client_for, db, tmp_path):
    from sqlalchemy import func, select
    from app import models
    from app.config import settings
    a = client_for("a@example.com")
    b = client_for("b@example.com")
    a.post("/api/checkins", {"emotion_id": "radost", "tag_ids": [a.get("/api/tags").json()[0]["id"]]})
    a.put("/api/days/2026-10-18", {"plan_status": "yes"})
    a.post("/api/tags", {"group": "with", "name": "Кот"})
    b.post("/api/checkins", {"emotion_id": "pokoy"})
    folder = settings.media_dir / "1"
    folder.mkdir(parents=True)
    (folder / "x.jpg").write_bytes(b"1")

    assert a.post("/api/account/wipe", {"password": "wrong"}).status_code == 403
    assert a.post("/api/account/wipe", {"password": "password123"}).status_code == 200
    assert a.get("/api/diary").json()["days"] == []
    assert not any(t["name"] == "Кот" for t in a.get("/api/tags").json())
    assert not folder.exists()
    assert len(b.get("/api/diary").json()["days"]) == 1
    assert db.scalar(select(func.count()).select_from(models.Checkin)) == 1
