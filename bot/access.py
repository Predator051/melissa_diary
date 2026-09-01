"""Доступ до бота: перший користувач стає власником, решту він підтверджує."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from . import db, keyboards
from .config import ALLOWED_USER_IDS

log = logging.getLogger(__name__)


def display_name(user: User) -> str:
    return user.full_name or (f"@{user.username}" if user.username else str(user.id))


def _chat_id(event: TelegramObject, user: User) -> int:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat.id
    return user.id


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.is_bot:
            return None

        name = display_name(user)
        chat_id = _chat_id(event, user)
        record = db.get_user(user.id)

        if user.id in ALLOWED_USER_IDS:
            record = db.upsert_user(user.id, chat_id, name, approved=1,
                                    is_owner=1 if db.owner() is None else 0)
        elif record is None and db.owner() is None:
            record = db.upsert_user(user.id, chat_id, name, approved=1, is_owner=1)
            log.info("Власником бота став %s (%s)", name, user.id)
        elif record is None:
            db.upsert_user(user.id, chat_id, name)
            await self._request_access(event, data, user, name)
            return None
        else:
            record = db.upsert_user(user.id, chat_id, name)

        if not record["approved"]:
            await self._deny(event, user)
            return None

        data["user_record"] = record
        data["user_name"] = name
        return await handler(event, data)

    async def _request_access(self, event, data, user: User, name: str) -> None:
        bot = data["bot"]
        owner = db.owner()
        if owner:
            try:
                await bot.send_message(
                    owner["chat_id"],
                    f"🔔 <b>{name}</b> (id <code>{user.id}</code>) просить доступ до бота.",
                    reply_markup=keyboards.approve_user_menu(user.id),
                )
            except Exception:  # noqa: BLE001 - власник міг заблокувати бота
                log.exception("Не вдалось повідомити власника про запит доступу")
        await self._deny(event, user)

    async def _deny(self, event: TelegramObject, user: User) -> None:
        text = (
            "🚫 Доступ до бота закритий.\n"
            f"Твій Telegram id: <code>{user.id}</code>\n"
            "Попроси власника бота підтвердити доступ."
        )
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ закритий", show_alert=True)
