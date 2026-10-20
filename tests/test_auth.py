def test_login_sets_httponly_secure_cookie(make_user, api):
    make_user("a@example.com")
    r = api.post("/api/auth/login", {"email": "A@example.com ", "password": "password123"})
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("feel_session="))
    assert "HttpOnly" in session and "Secure" in session and "samesite=lax" in session.lower()
    assert "Max-Age=7776000" in session  # 90 дней
    assert api.get("/api/auth/me").json()["email"] == "a@example.com"


def test_session_token_is_stored_hashed(make_user, api, db):
    from sqlalchemy import select
    from app import models
    make_user("a@example.com")
    api.login("a@example.com")
    token = api.c.cookies.get("feel_session")
    stored = db.scalars(select(models.UserSession.token_hash)).all()
    assert stored and token not in stored


def test_wrong_password(make_user, api):
    make_user("a@example.com")
    r = api.post("/api/auth/login", {"email": "a@example.com", "password": "nope"})
    assert r.status_code == 401


def test_login_requires_custom_header(make_user, api):
    make_user("a@example.com")
    r = api.c.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 403


def test_rate_limit_five_attempts(make_user, api):
    make_user("a@example.com")
    for _ in range(5):
        assert api.post("/api/auth/login", {"email": "a@example.com", "password": "x"}).status_code == 401
    r = api.post("/api/auth/login", {"email": "a@example.com", "password": "password123"})
    assert r.status_code == 429


def test_rate_limit_expires(make_user, api, db):
    from datetime import timedelta
    from sqlalchemy import update
    from app import models
    from app.timeutil import utcnow
    make_user("a@example.com")
    for _ in range(5):
        api.post("/api/auth/login", {"email": "a@example.com", "password": "x"})
    db.execute(update(models.LoginAttempt).values(created_at=utcnow() - timedelta(minutes=16)))
    db.commit()
    assert api.post("/api/auth/login", {"email": "a@example.com", "password": "password123"}).status_code == 200


def test_csrf_required_for_mutations(client_for):
    a = client_for("a@example.com")
    r = a.c.post("/api/checkins", json={"emotion_id": "radost"})
    assert r.status_code == 403
    r = a.c.post("/api/checkins", json={"emotion_id": "radost"}, headers={"X-CSRF-Token": "bad"})
    assert r.status_code == 403
    assert a.post("/api/checkins", {"emotion_id": "radost"}).status_code == 201


def test_unauthenticated(api):
    assert api.get("/api/today").status_code == 401


def test_logout(client_for):
    a = client_for("a@example.com")
    assert a.post("/api/auth/logout").status_code == 200
    assert a.get("/api/auth/me").status_code == 401


def test_registration_closed_by_default(api):
    r = api.post("/api/auth/register", {"email": "new@example.com", "password": "password123"})
    assert r.status_code == 403


def test_security_headers(api):
    r = api.get("/api/health")
    assert "max-age" in r.headers["strict-transport-security"]
    assert r.headers["cache-control"] == "no-store"


def test_http_redirects_to_https(api):
    r = api.c.get("/api/health", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].startswith("https://")
