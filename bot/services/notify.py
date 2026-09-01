"""Розсилка актуального розпорядку дня."""
from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot

from .. import db, keyboards
from ..config import BROADCAST
from .report import format_day

log = logging.getLogger(__name__)


async def push_day(bot: Bot, day: date, *, actor_id: int, highlight_id: int | None = None) -> None:
    """Надіслати повний розпорядок дня. Автору — завжди, іншим — якщо BROADCAST."""
    text = format_day(day, highlight_id=highlight_id)
    for user in db.approved_users():
        if user["user_id"] != actor_id and not BROADCAST:
            continue
        try:
            await bot.send_message(
                user["chat_id"], text, reply_markup=keyboards.summary_menu()
            )
        except Exception:  # noqa: BLE001 - хтось міг заблокувати бота
            log.exception("Не вдалось надіслати зведення користувачу %s", user["user_id"])
