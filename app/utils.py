"""Miscellaneous helper utilities."""
from __future__ import annotations

import math
import re
from aiogram import F
from aiogram.filters import StateFilter
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db import db
from app.keyboards import main_menu_kb
from app.states import TEXT_INPUT_STATES

__all__ = [
    "is_admin",
    "get_barber_status",
    "safe_answer",
    "safe_edit",
    "row_to_dict",
    "clean_text",
    "text_is",
    "NOT_TYPING",
    "delete_message_safe",
    "delete_previous_menu",
    "send_menu_message",
    "send_main_menu",
    "parse_text",
    "parse_phone",
    "parse_price",
    "parse_rating",
]


def clean_text(text: str | None) -> str:
    """Normalize text by stripping non-breaking spaces, emojis, variation selectors, and casing."""
    if not text:
        return ""
    t = text.replace("\u00a0", " ")
    # Strip emojis, pictographs, variation selectors (\ufe00-\ufe0f), etc.
    t = re.sub(r"[\U00010000-\U0010ffff\u200d\u2600-\u27bf\ufe00-\ufe0f]", "", t)
    return " ".join(t.split()).strip().lower()


def text_is(*targets: str):
    """Filter that matches message text against normalized target strings."""
    target_set = {clean_text(t) for t in targets}
    return F.text.func(lambda val: clean_text(val) in target_set)


def parse_text(message: Message, min_len: int = 1, max_len: int = 64) -> str | None:
    """Return stripped message text if it is plain text within the length limits."""
    text = (message.text or "").strip()
    if not (min_len <= len(text) <= max_len):
        return None
    return text


def parse_phone(message: Message) -> str | None:
    """Return the phone number if it contains 7–15 digits and only phone characters."""
    text = (message.text or "").strip()
    if not re.fullmatch(r"\+?[\d\s\-().]{7,25}", text):
        return None
    digits = re.sub(r"\D", "", text)
    if not 7 <= len(digits) <= 15:
        return None
    return text


def _parse_number(message: Message) -> float | None:
    raw = (message.text or "").replace(",", ".").replace("$", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_price(message: Message) -> float | None:
    """Return a positive finite price (<= 10000) or None."""
    value = _parse_number(message)
    if value is None or not 0 < value <= 10_000:
        return None
    return round(value, 2)


def parse_rating(message: Message) -> float | None:
    """Return a rating between 1 and 5 or None."""
    value = _parse_number(message)
    if value is None or not 1 <= value <= 5:
        return None
    return round(value, 1)


# Main-menu commands use this so they don't fire while the user is typing a
# name, bio, price, etc. (Cancel deliberately stays available everywhere.)
NOT_TYPING = ~StateFilter(*TEXT_INPUT_STATES)


def is_admin(user_id: int) -> bool:
    """Return True if the user is the configured admin."""
    return user_id == settings.admin_id


async def get_barber_status(user_id: int) -> str | None:
    """
    Return the barber status string for a user, or None if they
    have no barber record at all.
    """
    barber = await db.get_barber(user_id)
    if barber is None:
        return None
    return barber["status"]


async def safe_answer(
    callback: CallbackQuery, text: str | None = None, show_alert: bool = False
) -> None:
    """Answer a callback query, ignoring errors (e.g. query too old)."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except Exception:
        pass


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    **kwargs,
) -> None:
    """Edit a callback message text, with a fallback to send a new message."""
    try:
        if callback.message:
            await callback.message.edit_text(text, **kwargs)
    except Exception:
        if callback.message:
            await callback.message.answer(text, **kwargs)


def row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row to a plain dict."""
    if row is None:
        return {}
    return dict(row)


async def delete_message_safe(message: Message | None) -> None:
    """Safely delete a message if it exists, ignoring errors."""
    if message is None:
        return
    try:
        await message.delete()
    except Exception:
        pass


_last_menu_messages: dict[int, int] = {}


def _get_chat_id(event: Message | CallbackQuery) -> int | None:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat.id
    return None


async def delete_previous_menu(
    event: Message | CallbackQuery,
    state: FSMContext | None = None,
) -> None:
    """Delete any tracked previous menu message in this chat."""
    chat_id = _get_chat_id(event)
    bot = event.bot
    msg_id = None
    if chat_id and chat_id in _last_menu_messages:
        msg_id = _last_menu_messages.pop(chat_id, None)

    # Also check FSM state as a fallback
    if not msg_id and state is not None:
        try:
            data = await state.get_data()
            msg_id = data.get("last_menu_msg_id")
            if msg_id:
                await state.update_data(last_menu_msg_id=None)
        except Exception:
            pass

    if chat_id and bot and msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


async def send_menu_message(
    target: Message | CallbackQuery,
    state: FSMContext | None,
    text: str,
    reply_markup=None,
    delete_current: bool = True,
    **kwargs,
) -> Message | None:
    """
    Send a new menu message, deleting any tracked previous menu message.
    If called from an inline callback and delete_current is True, also deletes callback.message.
    Stores the newly sent message ID in both memory and FSM state.
    """
    await delete_previous_menu(target, state)

    if isinstance(target, CallbackQuery) and delete_current:
        await delete_message_safe(target.message)

    bot_or_msg = target if isinstance(target, Message) else target.message
    if bot_or_msg:
        sent = await bot_or_msg.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            **kwargs,
        )
        chat_id = _get_chat_id(target)
        if chat_id:
            _last_menu_messages[chat_id] = sent.message_id
        if state is not None:
            try:
                await state.update_data(last_menu_msg_id=sent.message_id)
            except Exception:
                pass
        return sent
    return None


async def send_main_menu(
    target: Message | CallbackQuery,
    state: FSMContext | None = None,
    text: str = "Main menu:",
    delete_menu: bool = True,
    clear_state: bool = True,
) -> Message | None:
    """
    Return to the main reply-keyboard menu with a short status/prompt text.
    Deletes any previously active inline menu messages so chat stays clean.
    Does NOT resend the long initial welcome text.
    """
    if delete_menu:
        await delete_previous_menu(target, state)
        if isinstance(target, CallbackQuery):
            await delete_message_safe(target.message)

    if clear_state and state is not None:
        try:
            await state.clear()
        except Exception:
            pass

    uid = target.from_user.id if target.from_user else 0
    barber_status = await get_barber_status(uid)
    admin = is_admin(uid)

    bot_or_msg = target if isinstance(target, Message) else target.message
    if bot_or_msg:
        return await bot_or_msg.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_admin=admin, barber_status=barber_status),
        )
    return None
