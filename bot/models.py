"""Типи подій. Дитина завжди в одному зі станів: годується, спить або не спить.
Кожна подія — це перехід у новий стан, тобто вона обриває попередній."""
from __future__ import annotations

FEED_LEFT = "feed_left"
FEED_RIGHT = "feed_right"
SLEEP = "sleep"
WAKE = "wake"

KINDS = (FEED_LEFT, FEED_RIGHT, SLEEP, WAKE)

LABEL = {
    FEED_LEFT: "Годування — ліва",
    FEED_RIGHT: "Годування — права",
    SLEEP: "Заснула",
    WAKE: "Встала",
}
SHORT = {FEED_LEFT: "Ліва", FEED_RIGHT: "Права", SLEEP: "Заснула", WAKE: "Встала"}
ICON = {FEED_LEFT: "🍼", FEED_RIGHT: "🍼", SLEEP: "😴", WAKE: "☀️"}

FEED = "feed"
ASLEEP = "asleep"
AWAKE = "awake"

STATE = {FEED_LEFT: FEED, FEED_RIGHT: FEED, SLEEP: ASLEEP, WAKE: AWAKE}
STATE_LABEL = {FEED: "годування", ASLEEP: "сон", AWAKE: "не спить"}


def title(kind: str) -> str:
    return f"{ICON[kind]} {LABEL[kind]}"


def short(kind: str) -> str:
    return f"{ICON[kind]} {SHORT[kind]}"
