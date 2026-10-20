"""Создание пользователя с настройками и метками по умолчанию, удаление данных."""
import shutil

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..security import hash_password

DEFAULT_MORNING_TEXT = "Ты составил план на день? Если нет — выдели полчаса"
DEFAULT_EVENING_TEXT = "Как себя чувствуешь? Как прошёл день? Запиши эмоции и мысли"

DEFAULT_TAGS = {
    "with": ["Один", "Партнёр", "Семья", "Дети", "Друзья", "Коллеги", "Незнакомые люди"],
    "where": ["Дома", "На работе", "В дороге", "На улице", "В гостях", "В кафе", "В спортзале"],
    "doing": ["Работа", "Учёба", "Отдых", "Спорт", "Домашние дела", "Общение", "Дорога",
              "Еда", "Хобби", "Экран и соцсети"],
}


def default_settings(user_id: int, timezone: str = None) -> models.UserSettings:
    return models.UserSettings(
        user_id=user_id,
        timezone=timezone or settings.default_timezone,
        morning_enabled=True, morning_time="08:30", morning_text=DEFAULT_MORNING_TEXT,
        evening_enabled=True, evening_time="21:30", evening_text=DEFAULT_EVENING_TEXT,
        repeat_enabled=True, repeat_after_min=60,
    )


def add_default_tags(db: Session, user_id: int) -> None:
    for group, names in DEFAULT_TAGS.items():
        for i, name in enumerate(names):
            db.add(models.Tag(user_id=user_id, group=group, name=name, sort=i))


def create_user(db: Session, email: str, password: str, is_admin: bool = False,
                timezone: str = None) -> models.User:
    email = email.strip().lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise ValueError("Пользователь с таким email уже есть")
    user = models.User(email=email, password_hash=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.flush()
    db.add(default_settings(user.id, timezone))
    add_default_tags(db, user.id)
    db.commit()
    return user


def user_media_dir(user_id: int):
    return settings.media_dir / str(user_id)


def wipe_user_data(db: Session, user_id: int) -> None:
    """«Удалить все данные»: физически стирает записи и файлы пользователя.

    Учётная запись остаётся; настройки и метки возвращаются к значениям по умолчанию.
    """
    db.execute(delete(models.Media).where(models.Media.user_id == user_id))
    checkin_ids = select(models.Checkin.id).where(models.Checkin.user_id == user_id)
    db.execute(delete(models.CheckinTag).where(models.CheckinTag.checkin_id.in_(checkin_ids)))
    db.execute(delete(models.Checkin).where(models.Checkin.user_id == user_id))
    db.execute(delete(models.DayLog).where(models.DayLog.user_id == user_id))
    db.execute(delete(models.Tag).where(models.Tag.user_id == user_id))
    db.execute(delete(models.NotificationLog).where(models.NotificationLog.user_id == user_id))
    old = db.get(models.UserSettings, user_id)
    tz_name = old.timezone if old else None
    if old:
        db.delete(old)
    db.flush()
    db.add(default_settings(user_id, tz_name))
    add_default_tags(db, user_id)
    db.commit()
    folder = user_media_dir(user_id)
    if folder.exists():
        shutil.rmtree(folder)
