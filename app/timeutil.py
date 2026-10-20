"""Работа со временем: в базе UTC без tzinfo, у пользователя — его часовой пояс."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def is_valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(tz(tz_name))


def local_date_of(dt_utc: datetime, tz_name: str) -> date:
    return to_local(dt_utc, tz_name).date()


def to_utc_naive(dt: datetime, tz_name: str) -> datetime:
    """Время с поясом → UTC naive. Время без пояса считается местным для пользователя."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz(tz_name))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def all_timezones() -> list:
    return sorted(available_timezones())
