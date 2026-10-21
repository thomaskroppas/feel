"""Фото и голосовые заметки: хранение на диске вне публичной папки, лимиты, квота."""
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

# mime → расширение файла. Фото сжимаются на устройстве в JPEG; голос на iOS — mp4/aac.
ALLOWED = {
    "photo": {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"},
    "audio": {"audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "aac",
              "audio/mpeg": "mp3", "audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav",
              "audio/x-wav": "wav", "video/mp4": "m4a"},
}
MAX_BYTES = {"photo": 8 * 1024 * 1024, "audio": 25 * 1024 * 1024}
MAX_PHOTOS = 4
MAX_AUDIO_SECONDS = 180


def normalize_mime(mime: Optional[str]) -> str:
    return (mime or "").split(";")[0].strip().lower()


def user_dir(user_id: int) -> Path:
    return settings.media_dir / str(user_id)


def new_relative_path(user_id: int, ext: str) -> str:
    return f"{user_id}/{uuid.uuid4().hex}.{ext}"


def absolute(m: models.Media) -> Path:
    return settings.media_dir / m.path


def used_bytes(db: Session, user_id: int) -> int:
    return db.scalar(select(func.coalesce(func.sum(models.Media.size), 0))
                     .where(models.Media.user_id == user_id)) or 0


def quota_bytes() -> int:
    return settings.user_quota_mb * 1024 * 1024


def remove_files(items: Iterable[models.Media]) -> None:
    for m in items:
        try:
            absolute(m).unlink()
        except FileNotFoundError:
            pass


def serialize(m: models.Media) -> dict:
    return {"id": m.id, "kind": m.kind, "mime": m.mime, "size": m.size,
            "duration_s": m.duration_s, "url": f"/api/media/{m.id}"}


def day_media(db: Session, user_id: int, start, end) -> List[models.Media]:
    return list(db.scalars(select(models.Media).where(
        models.Media.user_id == user_id, models.Media.day_log_date.is_not(None),
        models.Media.day_log_date >= start, models.Media.day_log_date <= end)
        .order_by(models.Media.id)))
