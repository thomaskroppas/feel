"""Пользователь Б не видит, не меняет и не удаляет данные пользователя А."""


def _setup(client_for):
    a = client_for("a@example.com")
    b = client_for("b@example.com")
    tag_a = a.post("/api/tags", {"group": "with", "name": "Секрет"}).json()
    c = a.post("/api/checkins", {"emotion_id": "radost", "note": "личное", "tag_ids": [tag_a["id"]],
                                 "occurred_at": "2026-10-15T10:00"}).json()
    a.put("/api/days/2026-10-15", {"plan_status": "yes", "plan_text": "план А"})
    return a, b, c, tag_a


def test_b_cannot_read_a(client_for):
    a, b, c, tag_a = _setup(client_for)
    assert b.get(f"/api/checkins/{c['id']}").status_code == 404
    assert b.get("/api/diary").json()["days"] == []
    day = b.get("/api/days/2026-10-15").json()
    assert day["checkins"] == [] and day["day_log"] is None
    assert all(t["id"] != tag_a["id"] for t in b.get("/api/tags").json())
    assert b.get(f"/api/diary?tag_id={tag_a['id']}").json()["days"] == []
    assert all(d["count"] == 0 for d in b.get("/api/today").json()["week"])


def test_b_cannot_modify_a(client_for):
    a, b, c, tag_a = _setup(client_for)
    assert b.patch(f"/api/checkins/{c['id']}", {"note": "взлом"}).status_code == 404
    assert b.delete(f"/api/checkins/{c['id']}").status_code == 404
    assert b.patch(f"/api/tags/{tag_a['id']}", {"name": "взлом"}).status_code == 404
    assert b.delete(f"/api/tags/{tag_a['id']}").status_code == 404
    # Нельзя прицепить чужую метку к своей записи.
    assert b.post("/api/checkins", {"emotion_id": "pokoy", "tag_ids": [tag_a["id"]]}).status_code == 422
    b_tags = [t["id"] for t in b.get("/api/tags").json() if t["group"] == "with"]
    assert b.put("/api/tags/order", {"group": "with", "ids": b_tags + [tag_a["id"]]}).status_code == 422
    # Б пишет свой день — день А не меняется.
    b.put("/api/days/2026-10-15", {"plan_text": "план Б"})
    assert a.get(f"/api/checkins/{c['id']}").json()["note"] == "личное"
    assert a.get("/api/days/2026-10-15").json()["day_log"]["plan_text"] == "план А"
    assert any(t["name"] == "Секрет" for t in a.get("/api/tags").json())


def test_settings_and_wipe_are_per_user(client_for):
    a, b, c, _ = _setup(client_for)
    b.put("/api/settings", {"morning_time": "06:00"})
    assert a.get("/api/settings").json()["morning_time"] == "08:30"
    b.post("/api/account/wipe", {"password": "password123"})
    assert a.get(f"/api/checkins/{c['id']}").status_code == 200


def test_push_subscriptions_are_per_user(client_for, fake_push):
    a, b, _, _ = _setup(client_for)
    sub = {"endpoint": "https://push.example/a", "keys": {"p256dh": "k", "auth": "x"}}
    a.post("/api/push/subscriptions", sub)
    assert b.post("/api/push/status", {"endpoint": sub["endpoint"]}).json() == {"devices": 0, "this_device": False}
    b.post("/api/push/unsubscribe", {"endpoint": sub["endpoint"]})
    assert a.post("/api/push/status", {"endpoint": sub["endpoint"]}).json()["devices"] == 1
    b.post("/api/push/test")
    assert fake_push.sent == []
