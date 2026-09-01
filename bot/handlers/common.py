"""Старт, довідка, зведення за день/вчора/тиждень, керування доступом."""
from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards
from ..services.report import format_day, format_week
from ..services.timeparse import now

router = Router(name="common")

HELP = (
    "🍼 <b>Щоденник дитини</b>\n\n"
    "Натисни <b>Годування</b> або <b>Сон</b>, обери подію — і впиши час, "
    "коли вона почалась (напр. <code>14:30</code>, <code>1430</code>) "
    "або натисни <b>Зараз</b>.\n\n"
    "Кожна подія триває до наступної: дитина або їсть, або спить, або не спить.\n\n"
    "<b>Команди</b>\n"
    "/today — розпорядок сьогодні\n"
    "/yesterday — розпорядок учора\n"
    "/week — підсумки за 7 днів\n"
    "/fix — виправити або видалити запис\n"
    "/users — хто має доступ (для власника)\n"
    "/help — ця довідка"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_name: str) -> None:
    await state.clear()
    await message.answer(
        f"Привіт, {user_name}! 👋\n\n{HELP}", reply_markup=keyboards.main_menu()
    )
    await message.answer(format_day(now().date()), reply_markup=keyboards.summary_menu())


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP, reply_markup=keyboards.main_menu())


@router.message(Command("today"))
@router.message(F.text == keyboards.BTN_TODAY)
async def cmd_today(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(format_day(now().date()), reply_markup=keyboards.summary_menu())


@router.message(Command("yesterday"))
@router.message(F.text.lower().in_({"вчора", "учора"}))
async def cmd_yesterday(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(format_day(now().date() - timedelta(days=1)))


@router.message(Command("week"))
@router.message(F.text.lower() == "тиждень")
async def cmd_week(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(format_week())


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, user_record) -> None:
    role = "власник" if user_record["is_owner"] else "користувач"
    await message.answer(f"Твій id: <code>{message.from_user.id}</code> ({role})")


@router.message(Command("users"))
async def cmd_users(message: Message, user_record) -> None:
    if not user_record["is_owner"]:
        await message.answer("Список користувачів бачить лише власник бота.")
        return
    lines = ["👥 <b>Користувачі</b>", ""]
    for user in db.all_users():
        status = "✅" if user["approved"] else "⏳"
        role = " (власник)" if user["is_owner"] else ""
        lines.append(f"{status} {user['name']}{role} — <code>{user['user_id']}</code>")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("ua:"))
async def approve(callback: CallbackQuery, user_record) -> None:
    if not user_record["is_owner"]:
        await callback.answer("Тільки власник бота", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    db.approve_user(user_id)
    user = db.get_user(user_id)
    await callback.message.edit_text(f"✅ Доступ надано: <b>{user['name']}</b>")
    await callback.bot.send_message(
        user["chat_id"],
        "✅ Тобі відкрито доступ до щоденника. Тисни /start.",
        reply_markup=keyboards.main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ur:"))
async def reject(callback: CallbackQuery, user_record) -> None:
    if not user_record["is_owner"]:
        await callback.answer("Тільки власник бота", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    db.revoke_user(user_id)
    await callback.message.edit_text("🚫 У доступі відмовлено.")
    await callback.answer()


@router.callback_query(F.data == "close")
async def close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()
    await callback.answer()
