from aiogram import Dispatcher

from . import common, edit, entry


def setup(dp: Dispatcher) -> None:
    """Порядок важливий: кнопки меню й команди мають перехоплювати ввід часу."""
    dp.include_router(common.router)
    dp.include_router(edit.router)
    dp.include_router(entry.router)
