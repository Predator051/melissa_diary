"""Додавання запису: вибір події -> ввід часу -> зведення за день."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards, models
from ..services.notify import push_day
from ..services.timeparse import TimeError, now, parse_time

router = Router(name="entry")

PROMPT = (
    "{title}\n\n"
    "О котрій це почалось? Напиши час — <code>14:30</code>, <code>1430</code>, "
    "<code>9:05</code> — або тисни «Зараз»."
)


class Add(StatesGroup):
    waiting_time = State()


@router.message(F.text == keyboards.BTN_FEED)
async def feed_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🍼 <b>Годування</b> — яка груди?", reply_markup=keyboards.feed_menu())


@router.message(F.text == keyboards.BTN_SLEEP)
async def sleep_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("😴 <b>Сон</b> — що сталось?", reply_markup=keyboards.sleep_menu())


@router.callback_query(F.data.startswith("k:"))
async def choose_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":", 1)[1]
    if kind not in models.KINDS:
        await callback.answer("Невідома подія", show_alert=True)
        return
    await state.set_state(Add.waiting_time)
    await state.update_data(kind=kind, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        PROMPT.format(title=f"<b>{models.title(kind)}</b>"),
        reply_markup=keyboards.time_menu(),
    )
    await callback.answer()


@router.callback_query(Add.waiting_time, F.data == "now")
async def save_now(callback: CallbackQuery, state: FSMContext, user_name: str) -> None:
    data = await state.get_data()
    await state.clear()
    await _save(callback.message, data["kind"], now(), callback.from_user.id, user_name, edit=True)
    await callback.answer()


@router.callback_query(F.data == "abort")
async def abort(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()
    await callback.answer("Скасовано")


@router.message(Add.waiting_time, F.text)
async def save_typed_time(message: Message, state: FSMContext, user_name: str) -> None:
    data = await state.get_data()
    try:
        moment = parse_time(message.text)
    except TimeError as exc:
        await message.answer(
            f"⚠️ {exc}. Напиши час у форматі <code>14:30</code> "
            f"(або <code>31.08 23:50</code>, якщо це було раніше)."
        )
        return
    await state.clear()
    await _save(message, data["kind"], moment, message.from_user.id, user_name)


async def _save(message: Message, kind: str, moment, user_id: int, user_name: str,
                *, edit: bool = False) -> None:
    event_id = db.add_event(moment, kind, user_id, user_name)
    confirmation = (
        f"✅ Записано: {models.title(kind)} — "
        f"<b>{moment.strftime('%d.%m %H:%M')}</b>"
    )
    if edit:
        await message.edit_text(confirmation)
    else:
        await message.answer(confirmation, reply_markup=keyboards.main_menu())
    await push_day(message.bot, moment.date(), actor_id=user_id, highlight_id=event_id)
