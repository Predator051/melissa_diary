"""Побудова розпорядку дня і підсумків.

Модель: кожна подія відкриває стан (годування / сон / не спить), який триває
до наступної події. Тому тривалість рядка = час до наступного запису.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta

from .. import db, models
from .timeparse import human_date, human_duration, now, plural, short_date


@dataclass
class Segment:
    event: sqlite3.Row
    start: datetime        # початок відрізка в межах доби
    end: datetime          # кінець відрізка в межах доби
    carried: bool          # подія почалась у попередній добі
    open_ended: bool       # стан ще триває (наступної події немає)

    @property
    def kind(self) -> str:
        return self.event["kind"]

    @property
    def state(self) -> str:
        return models.STATE[self.kind]

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def _bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, dtime(0, 0))
    return start, start + timedelta(days=1)


def segments(day: date) -> list[Segment]:
    """Відрізки станів у межах доби, обрізані по її межах і по 'зараз'."""
    day_start, day_end = _bounds(day)
    horizon = min(day_end, max(now(), day_start))

    events = db.events_between(day_start, day_end)
    carried = db.event_before(day_start)
    chain = ([carried] if carried else []) + list(events)
    if not chain:
        return []

    result: list[Segment] = []
    for i, event in enumerate(chain):
        ev_ts = db.parse(event["ts"])
        if i + 1 < len(chain):
            next_ts, open_ended = db.parse(chain[i + 1]["ts"]), False
        else:
            following = db.event_after(ev_ts, event["id"])
            if following:
                next_ts, open_ended = db.parse(following["ts"]), False
            else:
                next_ts, open_ended = horizon, True
        start = max(ev_ts, day_start)
        end = min(next_ts, horizon)
        if end < start:
            end = start
        result.append(
            Segment(event, start, end, carried=(i == 0 and carried is not None), open_ended=open_ended)
        )
    return result


def totals(day: date) -> dict:
    """Підсумки доби: сон, годування, кількості."""
    data = {
        "sleep": timedelta(),
        "feed": timedelta(),
        "awake": timedelta(),
        "feeds": 0,
        "left": 0,
        "right": 0,
        "sleeps": 0,
        "longest_sleep": timedelta(),
    }
    for seg in segments(day):
        if seg.state == models.ASLEEP:
            data["sleep"] += seg.duration
            data["longest_sleep"] = max(data["longest_sleep"], seg.duration)
        elif seg.state == models.FEED:
            data["feed"] += seg.duration
        else:
            data["awake"] += seg.duration
        if seg.carried:
            continue
        if seg.kind == models.FEED_LEFT:
            data["feeds"] += 1
            data["left"] += 1
        elif seg.kind == models.FEED_RIGHT:
            data["feeds"] += 1
            data["right"] += 1
        elif seg.kind == models.SLEEP:
            data["sleeps"] += 1
    return data


def format_day(day: date, *, highlight_id: int | None = None) -> str:
    segs = segments(day)
    header = f"📅 <b>{human_date(day)}</b>"
    if not segs:
        return f"{header}\n\nЗаписів немає."

    lines = [header, ""]
    for seg in segs:
        duration = human_duration(seg.duration)
        if seg.carried:
            since = db.parse(seg.event['ts']).strftime("%H:%M")
            lines.append(
                f"🌙 <i>з ночі: {models.STATE_LABEL[seg.state]} з {since} — {duration}</i>"
            )
            continue
        mark = " ⬅️" if seg.event["id"] == highlight_id else ""
        if seg.open_ended:
            tail = "щойно, триває" if seg.duration < timedelta(minutes=1) else f"{duration}, триває"
        else:
            tail = duration
        lines.append(
            f"<b>{seg.start.strftime('%H:%M')}</b>  {models.ICON[seg.kind]} "
            f"{models.SHORT[seg.kind]} — <i>{tail}</i>{mark}"
        )

    t = totals(day)
    lines += ["", "— <b>Разом за добу</b> —"]
    lines.append(f"🍼 Годувань: {t['feeds']} (ліва {t['left']} / права {t['right']})")
    if t["feed"]:
        lines.append(f"⏱ Часу на грудях: {human_duration(t['feed'])}")
    if not t["sleep"]:
        lines.append("😴 Сон: не записаний")
    if t["sleep"]:
        sleep_line = f"😴 Сон: {human_duration(t['sleep'])}"
        if t["sleeps"]:
            sleep_line += f" за {t['sleeps']} {plural(t['sleeps'], ('раз', 'рази', 'разів'))}"
        lines.append(sleep_line)
    if t["longest_sleep"]:
        lines.append(f"🌙 Найдовший сон: {human_duration(t['longest_sleep'])}")

    if day == now().date():
        last_feed = _last_of(day, (models.FEED_LEFT, models.FEED_RIGHT))
        if last_feed:
            lines.append(
                f"\n🍼 Останнє годування: {last_feed.strftime('%H:%M')} "
                f"({human_duration(now() - last_feed)} тому)"
            )
    return "\n".join(lines)


def _last_of(day: date, kinds: tuple[str, ...]) -> datetime | None:
    day_start, day_end = _bounds(day)
    found = [e for e in db.events_between(day_start, day_end) if e["kind"] in kinds]
    return db.parse(found[-1]["ts"]) if found else None


def format_week(end_day: date | None = None) -> str:
    end_day = end_day or now().date()
    lines = ["📊 <b>Останні 7 днів</b>", ""]
    week = {"feeds": 0, "sleep": timedelta(), "days": 0}
    for offset in range(6, -1, -1):
        day = end_day - timedelta(days=offset)
        t = totals(day)
        if not t["feeds"] and not t["sleep"]:
            lines.append(f"<b>{short_date(day)}</b> — записів немає")
            continue
        week["feeds"] += t["feeds"]
        week["sleep"] += t["sleep"]
        week["days"] += 1
        lines.append(
            f"<b>{short_date(day)}</b> — 🍼 {t['feeds']} ({t['left']}/{t['right']})"
            f" · 😴 {human_duration(t['sleep'])}"
        )
    if week["days"]:
        avg_feeds = week["feeds"] / week["days"]
        avg_sleep = week["sleep"] / week["days"]
        lines += [
            "",
            "— <b>У середньому за день</b> —",
            f"🍼 Годувань: {avg_feeds:.1f}",
            f"😴 Сон: {human_duration(avg_sleep)}",
        ]
    return "\n".join(lines)
