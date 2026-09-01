"""Клавіатури. Нижнє меню — постійне, підменю — інлайн під повідомленням."""
from __future__ import annotations

import sqlite3

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import db, models

BTN_FEED = "🍼 Годування"
BTN_SLEEP = "😴 Сон"
BTN_TODAY = "📅 Сьогодні"
BTN_FIX = "✏️ Виправити"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FEED), KeyboardButton(text=BTN_SLEEP)],
            [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_FIX)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _row(*buttons: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(buttons)


def feed_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="⬅️ Ліва", callback_data=f"k:{models.FEED_LEFT}"),
            InlineKeyboardButton(text="Права ➡️", callback_data=f"k:{models.FEED_RIGHT}"),
        ),
        _row(InlineKeyboardButton(text="✖️ Закрити", callback_data="close")),
    ])


def sleep_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="😴 Заснула", callback_data=f"k:{models.SLEEP}"),
            InlineKeyboardButton(text="☀️ Встала", callback_data=f"k:{models.WAKE}"),
        ),
        _row(InlineKeyboardButton(text="✖️ Закрити", callback_data="close")),
    ])


def time_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="🕐 Зараз", callback_data="now"),
            InlineKeyboardButton(text="✖️ Скасувати", callback_data="abort"),
        ),
    ])


def summary_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="✏️ Виправити", callback_data="fix"),
            InlineKeyboardButton(text="↩️ Скасувати останній", callback_data="undo"),
        ),
    ])


def events_menu(events: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    rows = [
        _row(InlineKeyboardButton(
            text=f"{db.parse(e['ts']).strftime('%d.%m %H:%M')}  {models.short(e['kind'])}",
            callback_data=f"ev:{e['id']}",
        ))
        for e in events
    ]
    rows.append(_row(InlineKeyboardButton(text="✖️ Закрити", callback_data="close")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_actions(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="🕐 Змінити час", callback_data=f"evt:{event_id}"),
            InlineKeyboardButton(text="🔄 Змінити тип", callback_data=f"evk:{event_id}"),
        ),
        _row(InlineKeyboardButton(text="🗑 Видалити", callback_data=f"evd:{event_id}")),
        _row(InlineKeyboardButton(text="⬅️ До списку", callback_data="fix")),
    ])


def kind_menu(event_id: int) -> InlineKeyboardMarkup:
    rows = [
        _row(InlineKeyboardButton(text=models.short(kind), callback_data=f"evks:{event_id}:{kind}"))
        for kind in models.KINDS
    ]
    rows.append(_row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ev:{event_id}")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="🗑 Так, видалити", callback_data=f"evdy:{event_id}"),
            InlineKeyboardButton(text="⬅️ Ні", callback_data=f"ev:{event_id}"),
        ),
    ])


def approve_user_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _row(
            InlineKeyboardButton(text="✅ Дозволити", callback_data=f"ua:{user_id}"),
            InlineKeyboardButton(text="🚫 Відмовити", callback_data=f"ur:{user_id}"),
        ),
    ])
