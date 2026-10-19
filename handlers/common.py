"""Common handlers: /start, cancel, location, fallback."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import db
from app.keyboards import location_kb, main_menu_kb
from app.texts import BTN, MSG, SHOP_ADDRESS, SHOP_HOURS, SHOP_NAME
from app.utils import (
    delete_previous_menu,
    get_barber_status,
    is_admin,
    safe_answer,
    send_main_menu,
    send_menu_message,
    text_is,
    NOT_TYPING,
)

__all__ = ["router", "fallback_router"]

logger = logging.getLogger(__name__)
router = Router(name="common")
fallback_router = Router(name="fallback")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start — register user and show the initial welcome message with main menu."""
    await delete_previous_menu(message, state)
    await state.clear()
    user = message.from_user
    if user is None:
        return
    await db.ensure_user(user.id, user.username, user.full_name)
    if is_admin(user.id):
        await db.ensure_admin_barber(user.id)

    uid = user.id
    barber_status = await get_barber_status(uid)
    admin = is_admin(uid)
    await message.answer(
        MSG["welcome"].format(shop=SHOP_NAME),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=admin, barber_status=barber_status),
    )


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
@router.message(text_is(BTN["cancel"], "cancel", "отмена"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    """Cancel any active FSM state and return to main menu without re-sending the long welcome text."""
    await send_main_menu(message, state, text=MSG["cancelled"])


# ── Location ──────────────────────────────────────────────────────────────────

@router.message(text_is(BTN["location"], "location", "location & map", "map"), NOT_TYPING)
async def handle_location(message: Message, state: FSMContext) -> None:
    """Show the barbershop location and a Google Maps button, cleaning previous menus."""
    await send_menu_message(
        message,
        state,
        MSG["location"].format(
            shop=SHOP_NAME,
            address=SHOP_ADDRESS,
            hours=SHOP_HOURS,
        ),
        reply_markup=location_kb(),
    )


# ── Application Status (not yet barber) ──────────────────────────────────────

@router.message(text_is(BTN["app_status"], "application status", "status"), NOT_TYPING)
async def handle_app_status(message: Message, state: FSMContext) -> None:
    """Show barber application status."""
    await delete_previous_menu(message, state)
    uid = message.from_user.id if message.from_user else 0
    barber = await db.get_barber(uid)
    if barber is None:
        await message.answer(MSG["app_none"], parse_mode=ParseMode.HTML)
        return
    status = barber["status"]
    if status == "pending":
        text = MSG["app_pending"]
    elif status == "rejected":
        text = MSG["app_rejected"]
    elif status == "approved":
        text = MSG["already_barber"]
    else:
        text = MSG["app_none"]
    await message.answer(text, parse_mode=ParseMode.HTML)


# ── Fallback (MUST BE REGISTERED LAST IN DISPATCHER) ──────────────────────────

@fallback_router.message(StateFilter(None))
async def fallback_no_state(message: Message) -> None:
    """Catch-all for unrecognized messages outside any FSM state."""
    await message.answer(MSG["unknown"])


@fallback_router.message()
async def fallback_in_state(message: Message) -> None:
    """Text sent while a step expects a button press (e.g. choosing a service)."""
    await message.answer(MSG["use_buttons"])


@fallback_router.callback_query()
async def fallback_callback(callback: CallbackQuery) -> None:
    """Buttons of old menus: answer so the client's loading spinner stops."""
    await safe_answer(callback, MSG["stale_button"])
