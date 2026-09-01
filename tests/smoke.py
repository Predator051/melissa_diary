"""Офлайн-прогін сценаріїв: диспетчер справжній, мережа підмінена."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["BOT_TOKEN"] = "42:TEST"

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import (  # noqa: E402
    AnswerCallbackQuery, DeleteMessage, EditMessageText, GetMe, SendMessage,
)
from aiogram.types import CallbackQuery, Chat, Message, Update, User  # noqa: E402

from bot import handlers  # noqa: E402
from bot.access import AccessMiddleware  # noqa: E402

USER = User(id=100, is_bot=False, first_name="Мама")
CHAT = Chat(id=100, type="private")
SENT: list[str] = []


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self._msg_id = 1000

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="Bot", username="test_bot")
        if isinstance(method, SendMessage):
            SENT.append(f"[send] {method.text}")
            self._msg_id += 1
            return Message(message_id=self._msg_id, date=datetime.now(), chat=CHAT,
                           text=method.text).as_(bot)
        if isinstance(method, EditMessageText):
            SENT.append(f"[edit] {method.text}")
            return Message(message_id=method.message_id or 1, date=datetime.now(), chat=CHAT,
                           text=method.text).as_(bot)
        if isinstance(method, (AnswerCallbackQuery, DeleteMessage)):
            return True
        return True


def message(text: str, uid: int = 1) -> Update:
    return Update(update_id=uid, message=Message(
        message_id=uid, date=datetime.now(), chat=CHAT, from_user=USER, text=text))


def press(data: str, uid: int = 1) -> Update:
    msg = Message(message_id=900, date=datetime.now(), chat=CHAT, text="меню")
    return Update(update_id=uid, callback_query=CallbackQuery(
        id=str(uid), from_user=USER, chat_instance="ci", message=msg, data=data))


async def main() -> None:
    bot = Bot(token="42:TEST", session=FakeSession(),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())
    handlers.setup(dp)

    script = [
        ("/start", message("/start")),
        ("кнопка Годування", message("🍼 Годування")),
        ("вибір Ліва", press("k:feed_left")),
        ("час 06:40", message("06:40")),
        ("кнопка Сон", message("😴 Сон")),
        ("вибір Заснула", press("k:sleep")),
        ("час 09:10", message("09:10")),
        ("кнопка Сон", message("😴 Сон")),
        ("вибір Встала", press("k:wake")),
        ("час зараз", press("now")),
        ("хибний час", message("🍼 Годування")),
        ("вибір Права", press("k:feed_right")),
        ("ввід 'абракадабра'", message("абракадабра")),
        ("ввід 25:99", message("25:99")),
        ("ввід 11:20", message("11:20")),
        ("/today", message("/today")),
        ("/week", message("/week")),
        ("/fix", message("/fix")),
    ]
    for label, update in script:
        SENT.clear()
        await dp.feed_update(bot, update)
        print(f"\n=== {label} " + "=" * (40 - len(label)))
        for item in SENT:
            print(item)

    # виправлення часу останнього запису
    from bot import db
    last = db.last_event()
    for label, update in [
        ("картка запису", press(f"ev:{last['id']}")),
        ("змінити час", press(f"evt:{last['id']}")),
        ("новий час 12:00", message("12:00")),
        ("підтвердження видалення", press(f"evd:{last['id']}")),
        ("видалити", press(f"evdy:{last['id']}")),
    ]:
        SENT.clear()
        await dp.feed_update(bot, update)
        print(f"\n=== {label} " + "=" * (40 - len(label)))
        for item in SENT:
            print(item)

    print("\n=== стан бази ===")
    for row in db.recent_events():
        print(dict(row))
    await bot.session.close()


asyncio.run(main())
