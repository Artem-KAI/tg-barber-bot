import logging

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db import Database
from keyboards import main_keyboard

logger = logging.getLogger(__name__)


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception:
        logger.exception("Не удалось отправить сообщение %s", chat_id)
        return False


async def menu_markup(event: Message | CallbackQuery, db: Database, admin_id: int):
    user = event.from_user
    user_id = user.id if user else 0
    return main_keyboard(user_id, admin_id, db)


async def cancel_flow(
    event: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    await state.clear()
    await event.answer(
        "Действие отменено.",
        reply_markup=main_keyboard(event.from_user.id if event.from_user else 0, admin_id, db),
    )


def parse_usd(text: str) -> int | None:
    cleaned = (text or "").replace("$", "").replace(",", ".").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0 or value > 1000:
        return None
    return int(round(value))


def parse_rating(text: str) -> float | None:
    cleaned = (text or "").replace(",", ".").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value < 1 or value > 5:
        return None
    return round(value, 1)
