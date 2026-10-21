"""Фото и голос: загрузка, лимиты, квота, выдача только владельцу."""
from app.config import settings

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000
AUDIO = b"\x00\x00\x00\x18ftypM4A " + b"1" * 5000


def upload(client, kind="photo", data=JPEG, mime="image/jpeg", **fields):
    form = {"kind": kind, **{k: str(v) for k, v in fields.items()}}
    headers = {"X-CSRF-Token": client.c.cookies.get("feel_csrf")}
    return client.c.post("/api/media", data=form, files={"file": ("f", data, mime)}, headers=headers)


def test_photo_upload_and_download(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    r = upload(a, checkin_id=c["id"])
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["kind"] == "photo" and m["url"] == f"/api/media/{m['id']}"
    got = a.get(m["url"])
    assert got.status_code == 200 and got.content == JPEG and got.headers["content-type"] == "image/jpeg"
    assert a.get(f"/api/checkins/{c['id']}").json()["media"][0]["id"] == m["id"]
    # Файл лежит вне static/, в папке пользователя.
    files = list((settings.media_dir / "1").iterdir())
    assert len(files) == 1 and files[0].read_bytes() == JPEG


def test_photo_limit_and_formats(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    for _ in range(4):
        assert upload(a, checkin_id=c["id"]).status_code == 201
    assert upload(a, checkin_id=c["id"]).status_code == 422
    c2 = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    assert upload(a, checkin_id=c2["id"], mime="text/html").status_code == 415
    assert upload(a, checkin_id=c2["id"], data=b"").status_code == 422
    assert upload(a, kind="video", checkin_id=c2["id"]).status_code == 422


def test_audio_replaces_previous_and_range(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "pokoy"}).json()
    first = upload(a, "audio", AUDIO, "audio/mp4;codecs=mp4a.40.2", checkin_id=c["id"], duration_s=12.34).json()
    assert first["mime"] == "audio/mp4" and first["duration_s"] == 12.3
    second = upload(a, "audio", AUDIO, "audio/mp4", checkin_id=c["id"], duration_s=20).json()
    media = a.get(f"/api/checkins/{c['id']}").json()["media"]
    assert [m["id"] for m in media] == [second["id"]]
    assert a.get(first["url"]).status_code == 404
    part = a.get(second["url"], headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and len(part.content) == 10
    assert upload(a, "audio", AUDIO, "audio/mp4", checkin_id=c["id"], duration_s=400).status_code == 422


def test_day_voice_summary(client_for):
    a = client_for("a@example.com")
    r = upload(a, "audio", AUDIO, "audio/mp4", day_log_date="2026-10-18", duration_s=30)
    assert r.status_code == 201
    day = a.get("/api/days/2026-10-18").json()
    assert day["day_log"] is not None and day["media"][0]["kind"] == "audio"
    diary = a.get("/api/diary").json()["days"]
    assert diary[0]["media"][0]["id"] == r.json()["id"]


def test_needs_exactly_one_link(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    assert upload(a).status_code == 422
    assert upload(a, checkin_id=c["id"], day_log_date="2026-10-18").status_code == 422


def test_quota(client_for, monkeypatch):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    monkeypatch.setattr(settings, "user_quota_mb", 0)
    assert upload(a, checkin_id=c["id"]).status_code == 413
    assert not any((settings.media_dir / "1").glob("*"))


def test_delete_media_and_checkin_remove_files(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    m1 = upload(a, checkin_id=c["id"]).json()
    upload(a, checkin_id=c["id"])
    assert a.delete(f"/api/media/{m1['id']}").status_code == 200
    assert len(list((settings.media_dir / "1").iterdir())) == 1
    a.delete(f"/api/checkins/{c['id']}")
    assert list((settings.media_dir / "1").iterdir()) == []


def test_b_cannot_touch_a_media(client_for):
    a = client_for("a@example.com")
    b = client_for("b@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    m = upload(a, checkin_id=c["id"]).json()
    assert b.get(m["url"]).status_code == 404
    assert b.delete(m["url"]).status_code == 404
    assert upload(b, checkin_id=c["id"]).status_code == 404
    assert a.get(m["url"]).status_code == 200
    # Без входа тоже нельзя.
    from tests.conftest import Api
    assert Api().get(m["url"]).status_code == 401


def test_wipe_removes_media(client_for):
    a = client_for("a@example.com")
    c = a.post("/api/checkins", {"emotion_id": "radost"}).json()
    upload(a, checkin_id=c["id"])
    a.post("/api/account/wipe", {"password": "password123"})
    assert not (settings.media_dir / "1").exists()
    assert a.get("/api/media-usage").json()["used"] == 0
