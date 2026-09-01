"""Нічний сон.

Правила:
* Ніч — це блок сну, що переходить північ, або сон, який почався між 00:00 і 06:00.
* Сон, що почався ввечері й закінчився до півночі, — денний.
* Прокидання між 00:00 і 06:00 ніч не закривають: у суму йдуть тільки шматки сну.
* Перше «Встала» о 06:00 і пізніше закриває ніч — далі все денне.
* Годування без «Встала» зараховується в сон (дитина не прокидалась).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta

from .. import db, models
from .timeparse import now

EVENING_START = dtime(20, 0)     # вечірнє вкладання, яке ще не дійшло до півночі
MORNING_END = dtime(6, 0)        # «Встала» від цієї години закриває ніч
NO_WAKE_CAP = dtime(12, 0)       # підйом не записаний — не тягнемо ніч далі полудня
MAX_STEPS = 500                  # запобіжник від нескінченного циклу

FEEDS = (models.FEED_LEFT, models.FEED_RIGHT)


@dataclass
class Night:
    start: datetime
    end: datetime | None                      # None — ніч ще триває
    total: timedelta                          # сума шматків сну
    wakings: int                              # прокидань усередині ночі
    feeds: int                                # годувань усередині ночі
    intervals: list[tuple[datetime, datetime]] = field(default_factory=list)
    ongoing: bool = False
    wake_missing: bool = False                # підйом не записаний

    @property
    def span_end(self) -> datetime:
        return self.end or (self.intervals[-1][1] if self.intervals else self.start)


def _dreaming(event: sqlite3.Row | None) -> bool:
    """Чи спить дитина в цьому стані. Годування успадковує стан до нього."""
    return _chain_start(event) is not None


def _chain_start(event: sqlite3.Row | None) -> sqlite3.Row | None:
    """Подія «Заснула», з якої почався поточний сон (крізь нічні годування)."""
    cursor = event
    steps = 0
    while cursor is not None and cursor["kind"] in FEEDS and steps < MAX_STEPS:
        cursor = db.event_before(db.parse(cursor["ts"]), cursor["id"])
        steps += 1
    if cursor is not None and cursor["kind"] == models.SLEEP:
        return cursor
    return None


def _start_event(day: date) -> sqlite3.Row | None:
    """Подія, з якої починається ніч, що закінчується вранці day."""
    midnight = datetime.combine(day, dtime(0, 0))
    anchor = db.event_at_or_before(midnight)
    start = _chain_start(anchor) if anchor is not None else None

    if start is not None and midnight > now():
        # ніч ще не дійшла до півночі: вечірнім вкладанням вважаємо сон після 20:00
        evening = datetime.combine(day - timedelta(days=1), EVENING_START)
        if db.parse(start["ts"]) < evening:
            start = None

    if start is None:
        # дитина заснула вже після півночі, але до 06:00 — це теж ніч
        for event in db.events_between(midnight, datetime.combine(day, MORNING_END)):
            if event["kind"] == models.SLEEP:
                return event
    return start


def night_for_morning(day: date) -> Night | None:
    """Ніч, яка закінчилась уранці цього дня (або ще триває)."""
    start_event = _start_event(day)
    if start_event is None:
        return None

    morning_end = datetime.combine(day, MORNING_END)
    current = now()
    cap = min(current, datetime.combine(day, NO_WAKE_CAP))

    night = Night(start=db.parse(start_event["ts"]), end=None, total=timedelta(),
                  wakings=0, feeds=0)
    cursor = start_event
    awake_since: datetime | None = None

    for _ in range(MAX_STEPS):
        cur_ts = db.parse(cursor["ts"])
        following = db.event_after(cur_ts, cursor["id"])

        if following is None:
            seg_end = max(cur_ts, cap)
            if _dreaming(cursor):
                night.total += seg_end - cur_ts
                night.intervals.append((cur_ts, seg_end))
                night.ongoing = cap >= current
                night.wake_missing = not night.ongoing
                night.end = None if night.ongoing else seg_end
            else:
                night.end = awake_since or cur_ts
                if awake_since is not None:
                    night.wakings -= 1
            break

        next_ts = db.parse(following["ts"])

        if awake_since is not None and next_ts > morning_end:
            # дитина не спить і вже ранок — ніч закінчилась на цьому підйомі
            night.end = awake_since
            night.wakings -= 1
            break

        if _dreaming(cursor):
            night.total += next_ts - cur_ts
            night.intervals.append((cur_ts, next_ts))

        if following["kind"] == models.WAKE:
            if next_ts >= morning_end:
                night.end = next_ts
                break
            night.wakings += 1
            awake_since = next_ts
        elif following["kind"] == models.SLEEP:
            awake_since = None
        elif following["kind"] in FEEDS:
            night.feeds += 1

        cursor = following

    if night.end is None and not night.ongoing:
        night.end = night.span_end
    night.wakings = max(night.wakings, 0)
    return night


def night_started_on(day: date) -> Night | None:
    """Ніч, яка почалась увечері цього дня (для сьогоднішньої сводки — та, що триває)."""
    night = night_for_morning(day + timedelta(days=1))
    if night is None or night.start.date() != day:
        return None
    return night


def spans_for_day(day: date) -> list[tuple[datetime, datetime]]:
    """Проміжки доби, зайняті ніччю: з них денний сон не рахуємо."""
    spans = []
    for night in (night_for_morning(day), night_started_on(day)):
        if night is not None:
            spans.append((night.start, night.span_end))
    return spans
