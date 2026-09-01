"""SQLite-сховище. Один файл, стандартна бібліотека, без ORM.

Час подій зберігаємо як локальний київський час рядком 'YYYY-MM-DD HH:MM'
(лексикографічне сортування збігається з хронологічним).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Optional

from .config import DB_PATH

TS_FMT = "%Y-%m-%d %H:%M"

_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    author_id   INTEGER NOT NULL,
    author_name TEXT,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    chat_id   INTEGER NOT NULL,
    name      TEXT,
    approved  INTEGER NOT NULL DEFAULT 0,
    is_owner  INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT NOT NULL
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def fmt(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def parse(ts: str) -> datetime:
    return datetime.strptime(ts, TS_FMT)


# ---------- події ----------

def add_event(dt: datetime, kind: str, author_id: int, author_name: str) -> int:
    cur = conn().execute(
        "INSERT INTO events (ts, kind, author_id, author_name, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (fmt(dt), kind, author_id, author_name, datetime.now().strftime(TS_FMT)),
    )
    conn().commit()
    return int(cur.lastrowid)


def get_event(event_id: int) -> Optional[sqlite3.Row]:
    return conn().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()


def update_event(event_id: int, *, dt: datetime | None = None, kind: str | None = None) -> None:
    if dt is not None:
        conn().execute("UPDATE events SET ts = ? WHERE id = ?", (fmt(dt), event_id))
    if kind is not None:
        conn().execute("UPDATE events SET kind = ? WHERE id = ?", (kind, event_id))
    conn().commit()


def delete_event(event_id: int) -> None:
    conn().execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn().commit()


def events_between(start: datetime, end: datetime) -> list[sqlite3.Row]:
    """Події в проміжку [start, end)."""
    return conn().execute(
        "SELECT * FROM events WHERE ts >= ? AND ts < ? ORDER BY ts, id",
        (fmt(start), fmt(end)),
    ).fetchall()


def event_before(dt: datetime, before_id: int | None = None) -> Optional[sqlite3.Row]:
    """Остання подія строго раніше dt (для однакового часу — з меншим id)."""
    if before_id is None:
        return conn().execute(
            "SELECT * FROM events WHERE ts < ? ORDER BY ts DESC, id DESC LIMIT 1", (fmt(dt),)
        ).fetchone()
    return conn().execute(
        "SELECT * FROM events WHERE ts < ? OR (ts = ? AND id < ?) ORDER BY ts DESC, id DESC LIMIT 1",
        (fmt(dt), fmt(dt), before_id),
    ).fetchone()


def event_at_or_before(dt: datetime) -> Optional[sqlite3.Row]:
    """Подія, що визначає стан дитини в момент dt."""
    return conn().execute(
        "SELECT * FROM events WHERE ts <= ? ORDER BY ts DESC, id DESC LIMIT 1", (fmt(dt),)
    ).fetchone()


def event_after(dt: datetime, after_id: int | None = None) -> Optional[sqlite3.Row]:
    """Перша подія строго пізніше dt (для однакового часу — з більшим id)."""
    if after_id is None:
        return conn().execute(
            "SELECT * FROM events WHERE ts > ? ORDER BY ts, id LIMIT 1", (fmt(dt),)
        ).fetchone()
    return conn().execute(
        "SELECT * FROM events WHERE ts > ? OR (ts = ? AND id > ?) ORDER BY ts, id LIMIT 1",
        (fmt(dt), fmt(dt), after_id),
    ).fetchone()


def last_event() -> Optional[sqlite3.Row]:
    return conn().execute("SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT 1").fetchone()


def recent_events(limit: int = 12) -> list[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------- користувачі ----------

def upsert_user(user_id: int, chat_id: int, name: str, *, approved: int = 0,
                is_owner: int = 0) -> sqlite3.Row:
    conn().execute(
        "INSERT INTO users (user_id, chat_id, name, approved, is_owner, joined_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET chat_id = excluded.chat_id, name = excluded.name,"
        " approved = MAX(users.approved, excluded.approved),"
        " is_owner = MAX(users.is_owner, excluded.is_owner)",
        (user_id, chat_id, name, approved, is_owner, datetime.now().strftime(TS_FMT)),
    )
    conn().commit()
    return get_user(user_id)


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    return conn().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def approve_user(user_id: int) -> None:
    conn().execute("UPDATE users SET approved = 1 WHERE user_id = ?", (user_id,))
    conn().commit()


def revoke_user(user_id: int) -> None:
    conn().execute("UPDATE users SET approved = 0 WHERE user_id = ? AND is_owner = 0", (user_id,))
    conn().commit()


def owner() -> Optional[sqlite3.Row]:
    return conn().execute("SELECT * FROM users WHERE is_owner = 1 LIMIT 1").fetchone()


def approved_users() -> list[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM users WHERE approved = 1 ORDER BY joined_at"
    ).fetchall()


def all_users() -> list[sqlite3.Row]:
    return conn().execute("SELECT * FROM users ORDER BY joined_at").fetchall()
