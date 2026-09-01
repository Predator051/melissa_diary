"""Побудова розпорядку дня і підсумків.

Модель: кожна подія відкриває стан (годування / сон / не спить), який триває
до наступної події. Тому тривалість рядка = час до наступного запису.
Нічний сон рахується окремо — див. night.py.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta

from .. import db, models
from . import night as night_service
from .timeparse import human_date, human_duration, now, plural, short_date

Interval = tuple[datetime, datetime]


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


def _subtract(intervals: list[Interval], spans: list[Interval]) -> list[Interval]:
    """Прибрати з відрізків усе, що потрапляє в spans (проміжки ночі)."""
    result: list[Interval] = []
    for start, end in intervals:
        pieces = [(start, end)]
        for span_start, span_end in spans:
            remaining: list[Interval] = []
            for piece_start, piece_end in pieces:
                if span_end <= piece_start or span_start >= piece_end:
                    remaining.append((piece_start, piece_end))
                    continue
                if piece_start < span_start:
                    remaining.append((piece_start, span_start))
                if span_end < piece_end:
                    remaining.append((span_end, piece_end))
            pieces = remaining
        result.extend(piece for piece in pieces if piece[1] > piece[0])
    return result


def totals(day: date) -> dict:
    """Підсумки доби: денний сон окремо, нічний окремо."""
    morning_night = night_service.night_for_morning(day)
    evening_night = night_service.night_started_on(day)
    spans = night_service.spans_for_day(day)

    sleep_intervals: list[Interval] = []
    data = {
        "feed": timedelta(),
        "feeds": 0,
        "left": 0,
        "right": 0,
        "night_feeds": 0,
        "day_sleep": timedelta(),
        "naps": 0,
        "longest_nap": timedelta(),
        "night": morning_night,
        "evening_night": evening_night,
    }

    for seg in segments(day):
        if seg.state == models.ASLEEP:
            sleep_intervals.append((seg.start, seg.end))
        elif seg.state == models.FEED:
            data["feed"] += seg.duration
        if seg.carried:
            continue
        if seg.kind in (models.FEED_LEFT, models.FEED_RIGHT):
            data["feeds"] += 1
            data["left" if seg.kind == models.FEED_LEFT else "right"] += 1
            if morning_night is not None and morning_night.start <= seg.start < morning_night.span_end:
                data["night_feeds"] += 1

    day_sleep = _subtract(sleep_intervals, spans)
    data["day_sleep"] = sum((end - start for start, end in day_sleep), timedelta())
    data["naps"] = len(day_sleep)
    data["longest_nap"] = max((end - start for start, end in day_sleep), default=timedelta())
    return data


def _night_headline(day: date, night: night_service.Night) -> str:
    started = night.start.strftime("%H:%M")
    if night.start.date() != day:
        started += f" ({night.start.strftime('%d.%m')})"
    wakings = (
        f" · прокидалась {night.wakings} {plural(night.wakings, ('раз', 'рази', 'разів'))}"
        if night.wakings else ""
    )
    if night.ongoing:
        return f"🌙 <i>Ніч триває з {started}{wakings}</i>"
    if night.wake_missing:
        return f"🌙 <i>Ніч: {started} → підйом не записаний{wakings}</i>"
    return f"🌙 <i>Ніч: {started} → {night.span_end.strftime('%H:%M')}{wakings}</i>"


def format_day(day: date, *, highlight_id: int | None = None) -> str:
    segs = segments(day)
    t = totals(day)
    night = t["night"]

    lines = [f"📅 <b>{human_date(day)}</b>"]
    if night is not None:
        lines.append(_night_headline(day, night))
    if not segs:
        lines += ["", "Записів немає."]
        return "\n".join(lines)
    lines.append("")

    for seg in segs:
        duration = human_duration(seg.duration)
        if seg.carried:
            if night is not None and night.start <= db.parse(seg.event["ts"]) < night.span_end:
                continue  # ця подія вже описана рядком про ніч
            since = db.parse(seg.event["ts"]).strftime("%H:%M")
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

    lines += ["", "— <b>Разом за добу</b> —"]
    feeds_line = f"🍼 Годувань: {t['feeds']} (ліва {t['left']} / права {t['right']})"
    if t["night_feeds"]:
        feeds_line += f", з них уночі {t['night_feeds']}"
    lines.append(feeds_line)
    if t["feed"]:
        lines.append(f"⏱ Часу на грудях: {human_duration(t['feed'])}")

    if night is not None:
        suffix = " (триває)" if night.ongoing else ""
        lines.append(f"🌙 Нічний сон: {human_duration(night.total)}{suffix}")
    else:
        lines.append("🌙 Нічний сон: не записаний")

    if t["day_sleep"]:
        day_line = (
            f"😴 Денний сон: {human_duration(t['day_sleep'])} за {t['naps']} "
            f"{plural(t['naps'], ('раз', 'рази', 'разів'))}"
        )
        lines.append(day_line)
        if t["naps"] > 1:
            lines.append(f"⭐ Найдовший денний сон: {human_duration(t['longest_nap'])}")
    else:
        lines.append("😴 Денний сон: не записаний")

    evening = t["evening_night"]
    if evening is not None:
        if evening.ongoing:
            lines.append(
                f"\n🌙 Вкладена о {evening.start.strftime('%H:%M')} — "
                f"ніч триває {human_duration(evening.total)}"
            )
        else:
            morning = (day + timedelta(days=1)).strftime("%d.%m")
            lines.append(
                f"\n🌙 Вкладена о {evening.start.strftime('%H:%M')} — "
                f"ця ніч у зведенні за {morning}"
            )

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
    week = {"feeds": 0, "day_sleep": timedelta(), "night_sleep": timedelta(),
            "days": 0, "nights": 0}

    for offset in range(6, -1, -1):
        day = end_day - timedelta(days=offset)
        t = totals(day)
        night = t["night"]
        night_total = night.total if night is not None else timedelta()
        if not t["feeds"] and not t["day_sleep"] and not night_total:
            lines.append(f"<b>{short_date(day)}</b> — записів немає")
            continue
        week["feeds"] += t["feeds"]
        week["day_sleep"] += t["day_sleep"]
        week["days"] += 1
        if night is not None:
            week["night_sleep"] += night_total
            week["nights"] += 1
        lines.append(
            f"<b>{short_date(day)}</b> — 🍼 {t['feeds']} ({t['left']}/{t['right']})"
            f" · 🌙 {human_duration(night_total) if night_total else '—'}"
            f" · 😴 {human_duration(t['day_sleep']) if t['day_sleep'] else '—'}"
        )

    if week["days"]:
        lines += ["", "— <b>У середньому за день</b> —",
                  f"🍼 Годувань: {week['feeds'] / week['days']:.1f}"]
        if week["nights"]:
            lines.append(f"🌙 Нічний сон: {human_duration(week['night_sleep'] / week['nights'])}")
        lines.append(f"😴 Денний сон: {human_duration(week['day_sleep'] / week['days'])}")
    return "\n".join(lines)
