"""Admin panel handler."""
from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db import db
from app.formatters import format_barber_profile, format_booking_card, format_service_list
from app.keyboards import (
    admin_barber_actions_kb,
    admin_barber_list_kb,
    admin_bookings_kb,
    admin_panel_kb,
    admin_services_kb,
    cancel_kb,
)
from app.states import AdminFSM
from app.texts import BTN, MSG
from app.utils import (
    delete_message_safe,
    is_admin,
    parse_price,
    parse_rating,
    row_to_dict,
    safe_answer,
    send_main_menu,
    send_menu_message,
    text_is,
    NOT_TYPING,
)

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ── Admin filter ──────────────────────────────────────────────────────────────

class AdminFilter(Filter):
    """Only allow the configured admin user."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:  # type: ignore[override]
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return is_admin(user.id)


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


# ── Admin panel entry ─────────────────────────────────────────────────────────

@router.message(text_is(BTN["admin_panel"], "admin panel", "admin"), NOT_TYPING)
async def admin_panel_entry(message: Message, state: FSMContext) -> None:
    """Show admin panel main menu, deleting any previous menu message above."""
    await state.clear()
    await send_menu_message(
        message,
        state,
        MSG["admin_panel"],
        reply_markup=admin_panel_kb(),
    )


@router.callback_query(F.data == "admin:panel")
async def admin_panel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to admin panel, deleting previous menu message."""
    await safe_answer(callback)
    await send_menu_message(
        callback,
        state,
        MSG["admin_panel"],
        reply_markup=admin_panel_kb(),
    )


# ── Pending Applications ──────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:pending")
async def admin_pending(callback: CallbackQuery, state: FSMContext) -> None:
    """Show list of pending barber applications, deleting the menu message above."""
    await safe_answer(callback)
    await delete_message_safe(callback.message)
    pending = await db.get_pending_barbers()
    if not pending:
        await send_main_menu(callback, state, text=MSG["admin_no_pending"])
        return
    for barber in pending:
        card = format_barber_profile(row_to_dict(barber))
        username = barber["username"] or "—"
        header = f"<b>Application:</b> @{username}\n\n{card}"
        await callback.message.answer(  # type: ignore[union-attr]
            header,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_barber_actions_kb(barber["user_id"], barber["status"]),
        )


@router.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve_barber(callback: CallbackQuery, state: FSMContext) -> None:
    """Approve a barber application."""
    barber_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    barber = await db.get_barber(barber_user_id)
    if not barber or barber["status"] != "pending":
        await safe_answer(callback, MSG["stale_button"], show_alert=True)
        await delete_message_safe(callback.message)
        return
    await safe_answer(callback)
    await db.approve_barber(barber_user_id)
    try:
        await callback.bot.send_message(  # type: ignore[union-attr]
            chat_id=barber_user_id,
            text=MSG["notify_barber_approved"],
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("Could not notify barber %s: %s", barber_user_id, e)
    await send_main_menu(callback, state, text=MSG["admin_approved_ok"])


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_barber(callback: CallbackQuery, state: FSMContext) -> None:
    """Reject a barber application."""
    barber_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    barber = await db.get_barber(barber_user_id)
    if not barber or barber["status"] != "pending":
        await safe_answer(callback, MSG["stale_button"], show_alert=True)
        await delete_message_safe(callback.message)
        return
    await safe_answer(callback)
    await db.reject_barber(barber_user_id)
    try:
        await callback.bot.send_message(  # type: ignore[union-attr]
            chat_id=barber_user_id,
            text=MSG["notify_barber_rejected"],
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("Could not notify barber %s: %s", barber_user_id, e)
    await send_main_menu(callback, state, text=MSG["admin_rejected_ok"])


# ── All Barbers ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:barbers")
async def admin_all_barbers(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    barbers = await db.get_all_barbers()
    if not barbers:
        await send_main_menu(callback, state, text=MSG["admin_no_barbers"])
        return
    await send_menu_message(
        callback,
        state,
        "<b>All Barbers:</b>",
        reply_markup=admin_barber_list_kb(barbers),
    )


@router.callback_query(F.data.startswith("admin_barber:"))
async def admin_view_barber(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    barber_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    barber = await db.get_barber(barber_user_id)
    if not barber:
        await send_main_menu(callback, state, text=MSG["error"])
        return
    card = format_barber_profile(row_to_dict(barber))
    await send_menu_message(
        callback,
        state,
        card,
        reply_markup=admin_barber_actions_kb(
            barber_user_id, barber["status"], back_cb="admin:barbers"
        ),
    )


# ── All Bookings ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:bookings")
async def admin_all_bookings(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    bookings = await db.get_all_bookings()
    if not bookings:
        await send_main_menu(callback, state, text=MSG["admin_no_bookings"])
        return
    await send_menu_message(
        callback,
        state,
        "<b>All Bookings</b> (last 20):",
        reply_markup=admin_bookings_kb(bookings),
    )


@router.callback_query(F.data.startswith("admin_bk:"))
async def admin_view_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    booking_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    booking = await db.get_booking(booking_id)
    if not booking:
        await send_main_menu(callback, state, text=MSG["error"])
        return
    barber = await db.get_barber(booking["barber_id"])
    barber_name = barber["name"] if barber else "—"
    card = format_booking_card({**row_to_dict(booking), "barber_name": barber_name})
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["back"], callback_data="admin:bookings")
    ]])
    await send_menu_message(callback, state, card, reply_markup=back_kb)


# ── Studio Service Prices ─────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:prices")
async def admin_prices(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    services = await db.get_services()
    service_list = format_service_list(services)
    await send_menu_message(
        callback,
        state,
        MSG["admin_service_list"].format(list=service_list),
        reply_markup=admin_services_kb(services),
    )


@router.callback_query(F.data.startswith("admin_svc:"))
async def admin_edit_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    _, svc_id_str, svc_name = callback.data.split(":", 2)  # type: ignore[union-attr]
    svc_id = int(svc_id_str)
    await state.set_state(AdminFSM.set_service_price)
    await state.update_data(editing_service_id=svc_id, editing_service_name=svc_name)
    await delete_message_safe(callback.message)
    await callback.message.answer(  # type: ignore[union-attr]
        MSG["admin_enter_price"].format(service=escape(svc_name)),
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_kb(),
    )


@router.message(AdminFSM.set_service_price)
async def admin_edit_price_done(message: Message, state: FSMContext) -> None:
    price = parse_price(message)
    if price is None:
        await message.answer(MSG["invalid_price"])
        return
    data = await state.get_data()
    await db.update_service_price(data["editing_service_id"], price)
    await send_main_menu(
        message,
        state,
        text=MSG["admin_price_updated"].format(
            service=escape(data["editing_service_name"]), price=f"{price:.0f}"
        ),
    )


# ── Barber rating & removal ───────────────────────────────────────────────────

async def _approved_barber(callback: CallbackQuery):
    """Barber from callback data if still approved, else answer with an alert."""
    barber_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    barber = await db.get_barber(barber_user_id)
    if not barber or barber["status"] != "approved":
        await safe_answer(callback, MSG["stale_button"], show_alert=True)
        await delete_message_safe(callback.message)
        return None
    return barber


@router.callback_query(F.data.startswith("admin_rating:"))
async def admin_rating_start(callback: CallbackQuery, state: FSMContext) -> None:
    barber = await _approved_barber(callback)
    if not barber:
        return
    await safe_answer(callback)
    await state.set_state(AdminFSM.set_rating)
    await state.update_data(rating_barber_id=barber["user_id"])
    await delete_message_safe(callback.message)
    await callback.message.answer(  # type: ignore[union-attr]
        MSG["admin_enter_rating"].format(name=escape(barber["name"])),
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_kb(),
    )


@router.message(AdminFSM.set_rating)
async def admin_rating_done(message: Message, state: FSMContext) -> None:
    rating = parse_rating(message)
    if rating is None:
        await message.answer(MSG["invalid_rating"])
        return
    data = await state.get_data()
    await db.update_barber_field(data["rating_barber_id"], "rating", rating)
    await send_main_menu(message, state, text=MSG["admin_rating_updated"])


@router.callback_query(F.data.startswith("admin_remove:"))
async def admin_remove_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    barber = await _approved_barber(callback)
    if not barber:
        return
    if barber["user_id"] == settings.admin_id:
        # The admin's own barber record is recreated on every /start
        await safe_answer(callback, MSG["admin_cannot_remove_self"], show_alert=True)
        return
    await safe_answer(callback)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["admin_remove_yes"], callback_data=f"admin_remove_yes:{barber['user_id']}"),
        InlineKeyboardButton(text=BTN["back"], callback_data=f"admin_barber:{barber['user_id']}"),
    ]])
    await send_menu_message(
        callback, state, MSG["admin_remove_confirm"].format(name=escape(barber["name"])), reply_markup=kb
    )


@router.callback_query(F.data.startswith("admin_remove_yes:"))
async def admin_remove_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    barber = await _approved_barber(callback)
    if not barber or barber["user_id"] == settings.admin_id:
        return
    await safe_answer(callback)
    barber_id = barber["user_id"]
    for bk in await db.cancel_active_barber_bookings(barber_id):
        try:
            await callback.bot.send_message(  # type: ignore[union-attr]
                chat_id=bk["client_id"],
                text=MSG["notify_client_barber_left"].format(id=bk["id"]),
            )
        except Exception as e:
            logger.warning("Could not notify client %s: %s", bk["client_id"], e)
    await db.delete_barber(barber_id)
    try:
        await callback.bot.send_message(chat_id=barber_id, text=MSG["notify_barber_removed"])  # type: ignore[union-attr]
    except Exception as e:
        logger.warning("Could not notify barber %s: %s", barber_id, e)
    await send_main_menu(callback, state, text=MSG["admin_removed_ok"])
