"""Проверка настоящего pywebpush: ключи из gen-vapid, шифрование, обработка 410."""
import base64
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import models
from app.cli import cmd_gen_vapid
from app.config import settings
from app.services import push


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def vapid(monkeypatch, capsys):
    cmd_gen_vapid(None)
    lines = dict(l.split("=", 1) for l in capsys.readouterr().out.splitlines() if "=" in l)
    monkeypatch.setattr(settings, "vapid_private_key", lines["VAPID_PRIVATE_KEY"])
    return lines


def make_sub():
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    return models.PushSubscription(endpoint="https://web.push.apple.com/abc", p256dh=b64(pub),
                                   auth=b64(os.urandom(16)))


class Resp:
    def __init__(self, code):
        self.status_code = code
        self.text = ""
        self.reason = "Gone"
        self.headers = {}


def test_real_webpush_encrypts_and_signs(vapid, monkeypatch):
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        calls.append((url, data, headers))
        return Resp(201)

    monkeypatch.setattr("requests.post", fake_post)
    push._webpush_transport(make_sub(), '{"title":"t"}')
    url, data, headers = calls[0]
    assert url == "https://web.push.apple.com/abc"
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["authorization"].startswith("vapid t=")
    assert headers["ttl"] == str(push.TTL_SECONDS)
    assert len(vapid["VAPID_PUBLIC_KEY"]) == 87


def test_real_webpush_410_is_gone(vapid, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(410))
    with pytest.raises(push.PushGone):
        push._webpush_transport(make_sub(), "{}")


def test_real_webpush_500_is_failure(vapid, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(500))
    with pytest.raises(push.PushFailed):
        push._webpush_transport(make_sub(), "{}")
