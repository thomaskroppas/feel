"""Настройки приложения. Всё берётся из переменных окружения или файла .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    p = Path(raw) if raw else default
    return p if p.is_absolute() else BASE_DIR / p


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self.public_url = os.getenv("PUBLIC_URL", "https://feel.meowtreach.com").rstrip("/")
        self.secret_key = os.getenv("SECRET_KEY", "")
        self.var_dir = _path("VAR_DIR", BASE_DIR / "var")
        self.database_path = _path("DATABASE_PATH", self.var_dir / "feel.db")
        self.media_dir = _path("MEDIA_DIR", self.var_dir / "media")
        self.static_dir = BASE_DIR / "static"
        self.emotions_file = BASE_DIR / "data" / "emotions.json"
        # Папка, куда панель хостинга кладёт проверочные файлы Let's Encrypt.
        # Passenger перехватывает все запросы, поэтому эти файлы отдаёт приложение.
        acme = os.getenv("ACME_DIR")
        self.acme_dir = Path(acme) if acme else None

        self.registration_open = _bool("REGISTRATION_OPEN", False)
        self.cookie_secure = _bool("COOKIE_SECURE", True)
        self.force_https = _bool("FORCE_HTTPS", True)
        self.session_days = int(os.getenv("SESSION_DAYS", "90"))
        self.login_max_attempts = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.login_window_min = int(os.getenv("LOGIN_WINDOW_MIN", "15"))
        self.user_quota_mb = int(os.getenv("USER_QUOTA_MB", "1024"))
        self.default_timezone = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")

        self.vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "")
        self.vapid_public_key = os.getenv("VAPID_PUBLIC_KEY", "")
        self.vapid_subject = os.getenv("VAPID_SUBJECT", "mailto:admin@meowtreach.com")

        # Не отправлять уведомление, если опоздали больше чем на столько минут.
        self.push_max_delay_min = int(os.getenv("PUSH_MAX_DELAY_MIN", "120"))

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


settings = Settings()
