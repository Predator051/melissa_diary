"""Перевірка правил нічного сну на сценаріях із ТЗ."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "night.db")
os.environ["BOT_TOKEN"] = "42:TEST"

from bot import db  # noqa: E402
from bot.services import night as night_service, report  # noqa: E402

FAKE_NOW = datetime(2026, 9, 1, 12, 0)


def _now() -> datetime:
    return FAKE_NOW


night_service.now = _now
report.now = _now

D0 = date(2026, 8, 31)   # вечір
D1 = date(2026, 9, 1)    # ранок


def setup(events: list[tuple[datetime, str]]) -> None:
    db.conn().execute("DELETE FROM events")
    db.conn().commit()
    for moment, kind in events:
        db.add_event(moment, kind, 1, "тест")


def ev(day: date, hh: int, mm: int) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm)


def hm(delta: timedelta) -> str:
    total = int(delta.total_seconds() // 60)
    return f"{total // 60}:{total % 60:02d}"


CASES = []


def case(name: str, events, *, night: str, day_sleep: str, day: date = D1,
         wakings: int = 0, night_feeds: int = 0, day_naps: int | None = None):
    CASES.append((name, events, night, day_sleep, day, wakings, night_feeds, day_naps))


case(
    "проста ніч",
    [(ev(D0, 21, 40), "sleep"), (ev(D1, 7, 5), "wake")],
    night="9:25", day_sleep="0:00",
)
case(
    "прокинулась уночі, годування після «Встала» не рахується",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 3, 0), "wake"), (ev(D1, 3, 20), "feed_left"),
     (ev(D1, 3, 40), "sleep"), (ev(D1, 7, 10), "wake")],
    night="9:30", day_sleep="0:00", wakings=1, night_feeds=1,
)
case(
    "годування без «Встала» — це сон",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 3, 0), "feed_left"), (ev(D1, 7, 10), "wake")],
    night="10:10", day_sleep="0:00", night_feeds=1,
)
case(
    "вечірній сон із підйомом до півночі — денний",
    [(ev(D0, 20, 30), "sleep"), (ev(D0, 22, 0), "wake"), (ev(D0, 23, 10), "sleep"),
     (ev(D1, 7, 0), "wake")],
    night="7:50", day_sleep="1:30", day=D0, day_naps=1,
)
case(
    "підйом після 06:00 закриває ніч, ранковий сон — денний",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 6, 30), "wake"), (ev(D1, 7, 0), "sleep"),
     (ev(D1, 9, 0), "wake")],
    night="9:30", day_sleep="2:00", day_naps=1,
)
case(
    "заснула до 20:00 — рахуємо весь сон",
    [(ev(D0, 19, 30), "sleep"), (ev(D1, 7, 0), "wake")],
    night="11:30", day_sleep="0:00",
)
case(
    "спала довше 09:00 — рахуємо весь сон",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 9, 40), "wake")],
    night="12:40", day_sleep="0:00",
)
case(
    "заснула після півночі",
    [(ev(D1, 0, 40), "sleep"), (ev(D1, 7, 0), "wake")],
    night="6:20", day_sleep="0:00",
)
case(
    "встала о 05:00 і більше не спить",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 5, 0), "wake"), (ev(D1, 8, 0), "feed_left")],
    night="8:00", day_sleep="0:00",
)
case(
    "денні сни не потрапляють у ніч",
    [(ev(D0, 21, 0), "sleep"), (ev(D1, 7, 0), "wake"), (ev(D1, 10, 0), "sleep"),
     (ev(D1, 11, 30), "wake")],
    night="10:00", day_sleep="1:30", day_naps=1,
)

failed = 0
for name, events, want_night, want_day, day, want_wakings, want_feeds, want_naps in CASES:
    setup(events)
    t = report.totals(day)
    n = t["night"] if day == D1 else night_service.night_for_morning(D1)
    got_night = hm(n.total) if n else "0:00"
    got_day = hm(t["day_sleep"])
    problems = []
    if got_night != want_night:
        problems.append(f"нічний сон {got_night} ≠ {want_night}")
    if got_day != want_day:
        problems.append(f"денний сон {got_day} ≠ {want_day}")
    if n and n.wakings != want_wakings:
        problems.append(f"прокидань {n.wakings} ≠ {want_wakings}")
    if day == D1 and t["night_feeds"] != want_feeds:
        problems.append(f"нічних годувань {t['night_feeds']} ≠ {want_feeds}")
    if want_naps is not None and t["naps"] != want_naps:
        problems.append(f"денних снів {t['naps']} ≠ {want_naps}")
    status = "✅" if not problems else "❌"
    span = f"{n.start.strftime('%d.%m %H:%M')} → {n.span_end.strftime('%H:%M')}" if n else "—"
    print(f"{status} {name}\n     ніч {got_night} ({span}), день {got_day}")
    for problem in problems:
        print(f"     ⚠️  {problem}")
        failed += 1

print("\nПомилок:", failed)
sys.exit(1 if failed else 0)
