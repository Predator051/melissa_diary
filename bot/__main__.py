"""Точка входу. Long polling — вебхуки й зовнішній вебсервер не потрібні."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from . import db, handlers
from .access import AccessMiddleware
from .config import BOT_TOKEN

COMMANDS = [
    BotCommand(command="today", description="Розпорядок сьогодні"),
    BotCommand(command="yesterday", description="Розпорядок учора"),
    BotCommand(command="week", description="Підсумки за 7 днів"),
    BotCommand(command="fix", description="Виправити або видалити запис"),
    BotCommand(command="users", description="Хто має доступ"),
    BotCommand(command="help", description="Довідка"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not BOT_TOKEN:
        sys.exit("BOT_TOKEN не заданий — заповни .env")

    db.conn()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())
    handlers.setup(dp)

    await bot.set_my_commands(COMMANDS)
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logging.info("Запуск @%s", me.username)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
