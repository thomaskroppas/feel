"""Модель данных. Все пользовательские данные привязаны к user_id.

Время хранится в UTC (naive datetime), рядом — местная дата на момент записи.
"""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow

QUADRANTS = ("red", "yellow", "blue", "green")
TAG_GROUPS = ("with", "where", "doing")
CHECKIN_SOURCES = ("manual", "evening", "notification")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UserSettings(Base):
    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    morning_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    morning_time: Mapped[str] = mapped_column(String(5), default="08:30", nullable=False)
    morning_text: Mapped[str] = mapped_column(Text, nullable=False)
    evening_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    evening_time: Mapped[str] = mapped_column(String(5), default="21:30", nullable=False)
    evening_text: Mapped[str] = mapped_column(Text, nullable=False)
    repeat_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    repeat_after_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Emotion(Base):
    __tablename__ = "emotions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    quadrant: Mapped[str] = mapped_column(String(10), nullable=False)
    energy: Mapped[int] = mapped_column(Integer, nullable=False)
    pleasantness: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CheckinTag(Base):
    __tablename__ = "checkin_tags"

    checkin_id: Mapped[int] = mapped_column(
        ForeignKey("checkins.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    emotion_id: Mapped[str] = mapped_column(ForeignKey("emotions.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    emotion: Mapped[Emotion] = relationship(lazy="joined")
    tags: Mapped[List["Tag"]] = relationship(secondary="checkin_tags", lazy="selectin", order_by="Tag.sort")
    media: Mapped[List["Media"]] = relationship(lazy="selectin", order_by="Media.id",
                                                cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        CheckConstraint("source IN ('manual','evening','notification')", name="ck_checkins_source"),
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("\"group\" IN ('with','where','doing')", name="ck_tags_group"),
    )


class DayLog(Base):
    __tablename__ = "day_logs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    plan_status: Mapped[Optional[str]] = mapped_column(String(3))  # yes / no
    plan_text: Mapped[Optional[str]] = mapped_column(Text)
    sleep_hours: Mapped[Optional[float]] = mapped_column(Float)
    sleep_quality: Mapped[Optional[int]] = mapped_column(Integer)
    sport_type: Mapped[Optional[str]] = mapped_column(String(100))  # "" — спорта не было
    sport_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    day_summary: Mapped[Optional[str]] = mapped_column(Text)
    # Не из ТЗ: время напоминания «Напомнить через 30 минут» (UTC).
    plan_remind_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("plan_status IS NULL OR plan_status IN ('yes','no')", name="ck_day_logs_plan"),
    )


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    checkin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("checkins.id", ondelete="CASCADE"))
    day_log_date: Mapped[Optional[date]] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('photo','audio')", name="ck_media_kind"),
        CheckConstraint(
            "(checkin_id IS NULL) <> (day_log_date IS NULL)", name="ck_media_one_link"
        ),
    )


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Когда приложение открыло экран по этому уведомлению (см. /api/notifications/pending).
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("user_id", "kind", "local_date", name="uq_notification_log"),)


class LoginAttempt(Base):
    """Не из ТЗ: неудачные входы для ограничения 5 попыток за 15 минут.

    Хранится в базе, а не в памяти: на хостинге может работать несколько процессов.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
