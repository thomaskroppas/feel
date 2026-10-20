import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="feel-tests-"))
os.environ.update({
    "VAR_DIR": str(_TMP / "var"),
    "SECRET_KEY": "test-secret",
    "COOKIE_SECURE": "true",
    "PUBLIC_URL": "https://feel.example",
    "VAPID_PRIVATE_KEY": "test-key",
    "VAPID_PUBLIC_KEY": "test-public",
})

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as app_db  # noqa: E402
from app.config import BASE_DIR, settings  # noqa: E402
from app.services import push  # noqa: E402

TEMPLATE = _TMP / "template.db"


def _migrate(path: Path) -> None:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")


_migrate(TEMPLATE)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "feel.db"
    shutil.copy(TEMPLATE, path)
    monkeypatch.setattr(settings, "database_path", path)
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    app_db.init_engine(f"sqlite:///{path}")
    yield
    app_db.engine.dispose()


@pytest.fixture
def db():
    s = app_db.SessionLocal()
    yield s
    s.close()


class FakeTransport:
    def __init__(self):
        self.sent = []
        self.gone = set()

    def __call__(self, sub, data):
        if sub.endpoint in self.gone:
            raise push.PushGone("410")
        self.sent.append((sub.endpoint, data))


@pytest.fixture
def fake_push(monkeypatch):
    t = FakeTransport()
    monkeypatch.setattr(push, "transport", t)
    return t


class Api:
    """Клиент, который сам ставит заголовок CSRF."""

    def __init__(self):
        from app.main import app
        self.c = TestClient(app, base_url="https://testserver")

    def _headers(self):
        h = {"X-Requested-With": "feel"}
        token = self.c.cookies.get("feel_csrf")
        if token:
            h["X-CSRF-Token"] = token
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._headers(), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._headers(), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self._headers(), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._headers(), **kw)

    def login(self, email, password="password123"):
        r = self.post("/api/auth/login", {"email": email, "password": password})
        assert r.status_code == 200, r.text
        return self


@pytest.fixture
def make_user(db):
    from app.services.users import create_user

    def _make(email="a@example.com", password="password123", timezone="Europe/Moscow"):
        return create_user(db, email, password, timezone=timezone)
    return _make


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def client_for(make_user):
    def _client(email, timezone="Europe/Moscow"):
        make_user(email, timezone=timezone)
        return Api().login(email)
    return _client
