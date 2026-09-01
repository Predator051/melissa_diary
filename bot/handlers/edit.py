"""Виправлення й видалення записів."""
from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards, models
from ..services.notify import push_day
from ..services.report import format_day
from ..services.timeparse import TimeError, human_date, parse_time

router = Router(name="edit")

LIST_LIMIT = 12


class EditEvent(StatesGroup):
    waiting_time = State()


def _list_text(count: int) -> str:
    if not count:
        return "Записів ще немає — нема чого виправляти."
    return f"✏️ <b>Останні записи</b> ({count})\nОбери, який виправити:"


async def _show_list(target: Message) -> None:
    events = db.recent_events(LIST_LIMIT)
    await target.answer(_list_text(len(events)), reply_markup=keyboards.events_menu(events))


def _event_card(event) -> str:
    moment = db.parse(event["ts"])
    return (
        f"{models.title(event['kind'])}\n"
        f"🕐 <b>{moment.strftime('%d.%m %H:%M')}</b> · {human_date(moment.date())}\n"
        f"✍️ записав(ла): {event['author_name']}"
    )


@router.message(Command("fix"))
@router.message(F.text == keyboards.BTN_FIX)
async def cmd_fix(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_list(message)


@router.callback_query(F.data == "fix")
async def cb_fix(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    events = db.recent_events(LIST_LIMIT)
    await callback.message.answer(
        _list_text(len(events)), reply_markup=keyboards.events_menu(events)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ev:"))
async def show_event(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    event = db.get_event(int(callback.data.split(":")[1]))
    if event is None:
        await callback.message.edit_text("Цей запис уже видалено.")
        await callback.answer()
        return
    await callback.message.edit_text(
        _event_card(event), reply_markup=keyboards.event_actions(event["id"])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("evt:"))
async def ask_new_time(callback: CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.split(":")[1])
    event = db.get_event(event_id)
    if event is None:
        await callback.answer("Запис уже видалено", show_alert=True)
        return
    await state.set_state(EditEvent.waiting_time)
    await state.update_data(event_id=event_id)
    await callback.message.edit_text(
        f"{models.title(event['kind'])}\n\n"
        f"Зараз: <b>{db.parse(event['ts']).strftime('%d.%m %H:%M')}</b>\n"
        f"Напиши новий час — <code>14:30</code> або <code>31.08 23:50</code>."
    )
    await callback.answer()


@router.message(EditEvent.waiting_time, F.text)
async def apply_new_time(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event = db.get_event(data["event_id"])
    if event is None:
        await state.clear()
        await message.answer("Запис уже видалено.")
        return
    try:
        moment = parse_time(message.text)
    except TimeError as exc:
        await message.answer(f"⚠️ {exc}. Спробуй ще раз: <code>14:30</code>.")
        return
    await state.clear()
    old_day = db.parse(event["ts"]).date()
    db.update_event(event["id"], dt=moment)
    await message.answer(
        f"✅ Час змінено: {models.title(event['kind'])} — "
        f"<b>{moment.strftime('%d.%m %H:%M')}</b>"
    )
    await _push(message, message.from_user.id, {old_day, moment.date()}, event["id"])


@router.callback_query(F.data.startswith("evks:"))
async def apply_new_kind(callback: CallbackQuery) -> None:
    _, raw_id, kind = callback.data.split(":")
    event = db.get_event(int(raw_id))
    if event is None or kind not in models.KINDS:
        await callback.answer("Запис уже видалено", show_alert=True)
        return
    db.update_event(event["id"], kind=kind)
    day = db.parse(event["ts"]).date()
    await callback.message.edit_text(f"✅ Тип змінено на {models.title(kind)}")
    await _push(callback.message, callback.from_user.id, {day}, event["id"])
    await callback.answer()


@router.callback_query(F.data.startswith("evk:"))
async def ask_new_kind(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])
    if db.get_event(event_id) is None:
        await callback.answer("Запис уже видалено", show_alert=True)
        return
    await callback.message.edit_text(
        "На що замінити?", reply_markup=keyboards.kind_menu(event_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("evdy:"))
async def do_delete(callback: CallbackQuery) -> None:
    event = db.get_event(int(callback.data.split(":")[1]))
    if event is None:
        await callback.answer("Запис уже видалено", show_alert=True)
        return
    day = db.parse(event["ts"]).date()
    db.delete_event(event["id"])
    await callback.message.edit_text(
        f"🗑 Видалено: {models.title(event['kind'])} — "
        f"<b>{db.parse(event['ts']).strftime('%d.%m %H:%M')}</b>"
    )
    await _push(callback.message, callback.from_user.id, {day}, None)
    await callback.answer()


@router.callback_query(F.data.startswith("evd:"))
async def confirm_delete(callback: CallbackQuery) -> None:
    event = db.get_event(int(callback.data.split(":")[1]))
    if event is None:
        await callback.answer("Запис уже видалено", show_alert=True)
        return
    await callback.message.edit_text(
        f"Видалити цей запис?\n\n{_event_card(event)}",
        reply_markup=keyboards.confirm_delete(event["id"]),
    )
    await callback.answer()


@router.callback_query(F.data == "undo")
async def undo_last(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    event = db.last_event()
    if event is None:
        await callback.answer("Записів немає", show_alert=True)
        return
    await callback.message.answer(
        f"Скасувати останній запис?\n\n{_event_card(event)}",
        reply_markup=keyboards.confirm_delete(event["id"]),
    )
    await callback.answer()


async def _push(message: Message, user_id: int, days: set[date], highlight_id: int | None) -> None:
    for day in sorted(days):
        await push_day(message.bot, day, actor_id=user_id, highlight_id=highlight_id)
