"""Налаштування бота. Читаємо .env без зовнішніх залежностей."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Kyiv")


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BROADCAST = os.environ.get("BROADCAST", "1").strip() not in ("0", "false", "no", "")
DB_PATH = BASE_DIR / os.environ.get("DB_PATH", "data/child_bot.db")

ALLOWED_USER_IDS = {
    int(part)
    for part in os.environ.get("ALLOWED_USER_IDS", "").replace(";", ",").split(",")
    if part.strip().isdigit()
}
