"""Розбір часу, який мама вписує руками, і форматування тривалостей."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..config import TZ

WEEKDAYS = ("понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя")
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")
MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)

_TIME_RE = re.compile(r"^(\d{1,2})\s*[:.\-\s]?\s*(\d{2})$")
_DATE_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?$")


class TimeError(ValueError):
    """Не вдалось розібрати час."""


def now() -> datetime:
    """Поточний київський час без tzinfo (у базі всі часи локальні наївні)."""
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def parse_time(text: str, base: datetime | None = None) -> datetime:
    """'14:30', '1430', '14.30', 'зараз', '31.08 23:50' -> datetime.

    Якщо запис роблять уночі (до 06:00) про вечірній час (18:00+) — це вчора.
    Інший час у майбутньому вважаємо помилкою і просимо виправити.
    """
    base = base or now()
    raw = text.strip().lower().replace(",", " ")
    if raw in ("зараз", "сейчас", "now", "тепер"):
        return base

    day_shift = 0
    parts = raw.split()
    explicit_date: date | None = None

    while parts and parts[0] in ("вчора", "учора", "вчера"):
        day_shift -= 1
        parts.pop(0)
    while parts and parts[0] in ("сьогодні", "сегодня"):
        parts.pop(0)

    if len(parts) == 2:
        m = _DATE_RE.match(parts[0])
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            year = base.year if y is None else (2000 + int(y) if len(y) == 2 else int(y))
            try:
                explicit_date = date(year, mo, d)
            except ValueError as exc:
                raise TimeError("Такої дати не існує") from exc
            parts = parts[1:]

    if len(parts) != 1:
        raise TimeError("Незрозумілий формат")

    m = _TIME_RE.match(parts[0]) or _TIME_RE.match(parts[0].zfill(4))
    if not m:
        raise TimeError("Незрозумілий формат")
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        raise TimeError("Такого часу не буває")

    if explicit_date is not None:
        return datetime(explicit_date.year, explicit_date.month, explicit_date.day, hour, minute)

    result = base.replace(hour=hour, minute=minute) + timedelta(days=day_shift)
    if day_shift == 0 and result > base + timedelta(minutes=5):
        if base.hour < 6 and hour >= 18:
            result -= timedelta(days=1)  # запис уночі про вечір, що вже минув
        else:
            raise TimeError("Цей час ще не настав")
    return result


def human_duration(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "щойно"
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} год {minutes} хв"
    if hours:
        return f"{hours} год"
    return f"{minutes} хв"


def human_date(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()].capitalize()}, {day.day} {MONTHS[day.month - 1]}"


def short_date(day: date) -> str:
    return f"{WEEKDAYS_SHORT[day.weekday()]} {day.strftime('%d.%m')}"


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Українські форми множини: 1 раз / 2 рази / 5 разів."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]
