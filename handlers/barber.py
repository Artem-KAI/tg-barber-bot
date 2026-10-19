"""Barber cabinet handler — studio, schedule, days off, bookings."""
from __future__ import annotations

import datetime
import logging
from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db import db
from app.formatters import format_barber_profile, format_booking_card
from app.keyboards import (
    admin_barber_actions_kb,
    barber_booking_actions_kb,
    barber_incoming_kb,
    barber_prices_kb,
    barber_profile_kb,
    barber_service_pick_kb,
    barber_studio_kb,
    cancel_kb,
    days_off_kb,
    leave_confirm_kb,
    schedule_days_kb,
    schedule_slots_kb,
    segments_kb,
)
from app.states import BarberApplyFSM, BarberDaysOffFSM, BarberEditFSM, BarberScheduleFSM
from app.texts import BTN, MSG
from app.utils import (
    delete_message_safe,
    delete_previous_menu,
    parse_price,
    parse_text,
    row_to_dict,
    safe_answer,
    send_main_menu,
    send_menu_message,
    text_is,
    NOT_TYPING,
)

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = Router(name="barber")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _active_barber(callback: CallbackQuery, state: FSMContext):
    """
    Return the caller's barber row if it is approved. Otherwise answer the
    callback with an alert, drop the stale menu and return None.
    """
    uid = callback.from_user.id if callback.from_user else 0
    barber = await db.get_barber(uid)
    if barber and barber["status"] == "approved":
        return barber
    await safe_answer(callback, MSG["not_active_barber"], show_alert=True)
    await state.clear()
    await delete_message_safe(callback.message)
    return None


async def _barber_booking(
    callback: CallbackQuery, state: FSMContext, allowed: tuple[str, ...]
):
    """
    Return the booking from callback data if it belongs to the calling barber
    and its status is in `allowed`; otherwise answer with an alert and return None.
    """
    if not await _active_barber(callback, state):
        return None
    booking_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    booking = await db.get_booking(booking_id)
    if (
        not booking
        or booking["barber_id"] != callback.from_user.id
        or booking["status"] not in allowed
    ):
        await safe_answer(callback, MSG["booking_not_editable"], show_alert=True)
        return None
    await safe_answer(callback)
    return booking


async def _notify(event, chat_id: int, text: str, **kwargs) -> None:
    """Send a notification, logging (not raising) on failure."""
    try:
        await event.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, **kwargs)
    except Exception as e:
        logger.warning("Could not notify %s: %s", chat_id, e)


async def _set_booking_status(
    callback: CallbackQuery,
    state: FSMContext,
    allowed: tuple[str, ...],
    status: str,
    client_msg: str,
    done_text: str,
) -> None:
    """Move a booking to `status` if the transition is allowed, then notify the client."""
    booking = await _barber_booking(callback, state, allowed)
    if not booking:
        return
    await db.update_booking_status(booking["id"], status)
    await _notify(callback, booking["client_id"], MSG[client_msg].format(id=booking["id"]))
    await send_main_menu(callback, state, text=done_text)


async def _notify_client_updated(event, booking_id: int) -> None:
    booking = await db.get_booking(booking_id)
    if booking:
        barber = await db.get_barber(booking["barber_id"])
        card = format_booking_card(
            {**row_to_dict(booking), "barber_name": barber["name"] if barber else "—"}
        )
        await _notify(
            event, booking["client_id"], MSG["notify_client_updated"].format(id=booking_id, card=card)
        )


def _slot_weekday(slot_datetime: str) -> int:
    return datetime.date.fromisoformat(slot_datetime.split(" ")[0]).weekday()


def _conflict_text(conflicts) -> str:
    return MSG["schedule_conflict"].format(n=len(conflicts), first=conflicts[0]["slot_datetime"])


# ── Apply as barber ───────────────────────────────────────────────────────────

@router.message(text_is(BTN["become_barber"], "become a barber", "become barber"), NOT_TYPING)
async def become_barber_start(message: Message, state: FSMContext) -> None:
    """Start the barber application flow."""
    await delete_previous_menu(message, state)
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    barber = await db.get_barber(uid)
    if barber:
        status = barber["status"]
        if status == "pending":
            await message.answer(MSG["already_applied"], parse_mode=ParseMode.HTML)
            return
        if status == "approved":
            await message.answer(MSG["already_barber"], parse_mode=ParseMode.HTML)
            return
    await state.set_state(BarberApplyFSM.name)
    await message.answer(MSG["apply_name"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())


@router.message(BarberApplyFSM.name)
async def apply_got_name(message: Message, state: FSMContext) -> None:
    name = parse_text(message, min_len=2, max_len=64)
    if name is None:
        await message.answer(MSG["invalid_text"].format(max=64))
        return
    await state.update_data(apply_name=name)
    await state.set_state(BarberApplyFSM.bio)
    await message.answer(MSG["apply_bio"], parse_mode=ParseMode.HTML)


@router.message(BarberApplyFSM.bio)
async def apply_got_bio(message: Message, state: FSMContext) -> None:
    bio = parse_text(message, max_len=500)
    if bio is None:
        await message.answer(MSG["invalid_text"].format(max=500))
        return
    await state.update_data(apply_bio=bio)
    await state.set_state(BarberApplyFSM.segment)
    await message.answer(MSG["apply_segment"], parse_mode=ParseMode.HTML, reply_markup=segments_kb())


@router.callback_query(BarberApplyFSM.segment, F.data.startswith("seg:"))
async def apply_got_segment(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    segment = callback.data.split(":")[1]  # type: ignore[union-attr]
    data = await state.get_data()
    uid = callback.from_user.id if callback.from_user else 0
    username = callback.from_user.username if callback.from_user else None
    full_name = callback.from_user.full_name if callback.from_user else ""
    await db.ensure_user(uid, username, full_name)
    await db.create_barber_application(uid, data["apply_name"], data["apply_bio"], segment)

    # Notify admin
    try:
        text = (
            f"<b>New barber application:</b>\n"
            f"Name: <b>{escape(data['apply_name'])}</b>\n"
            f"User ID: <code>{uid}</code>\n"
            f"Bio: {escape(data['apply_bio'])}\n"
            f"Segment: {segment.capitalize()}"
        )
        await callback.bot.send_message(  # type: ignore[union-attr]
            chat_id=settings.admin_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_barber_actions_kb(uid, "pending"),
        )
    except Exception as e:
        logger.warning("Could not notify admin: %s", e)

    await send_main_menu(callback, state, text=MSG["apply_done"])


# ── Barber Studio entry point ─────────────────────────────────────────────────

@router.message(text_is(BTN["barber_studio"], "barber studio", "studio"), NOT_TYPING)
async def barber_studio_entry(message: Message, state: FSMContext) -> None:
    """Show the barber cabinet main menu, deleting any previous menu message."""
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    barber = await db.get_barber(uid)
    if not barber or barber["status"] != "approved":
        # Refresh the reply keyboard, it may still show an outdated Studio button
        await send_main_menu(message, state, text=MSG["not_active_barber"])
        return
    await send_menu_message(
        message,
        state,
        MSG["barber_studio"].format(name=escape(barber["name"])),
        reply_markup=barber_studio_kb(),
    )


@router.callback_query(F.data == "barber:studio")
async def barber_studio_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to barber studio inline menu, deleting previous menu message."""
    barber = await _active_barber(callback, state)
    if not barber:
        return
    await safe_answer(callback)
    await state.set_state(None)
    await send_menu_message(
        callback,
        state,
        MSG["barber_studio"].format(name=escape(barber["name"])),
        reply_markup=barber_studio_kb(),
    )


# ── Profile ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:profile")
async def barber_view_profile(callback: CallbackQuery, state: FSMContext) -> None:
    barber = await _active_barber(callback, state)
    if not barber:
        return
    await safe_answer(callback)
    card = format_barber_profile(row_to_dict(barber))
    await send_menu_message(
        callback,
        state,
        MSG["barber_profile"].format(card=card),
        reply_markup=barber_profile_kb(),
    )


# ── Edit name ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:edit_name")
async def barber_edit_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    await state.set_state(BarberEditFSM.name)
    await delete_message_safe(callback.message)
    await callback.message.answer(MSG["barber_enter_name"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())  # type: ignore[union-attr]


@router.message(BarberEditFSM.name)
async def barber_edit_name_done(message: Message, state: FSMContext) -> None:
    name = parse_text(message, min_len=2, max_len=64)
    if name is None:
        await message.answer(MSG["invalid_text"].format(max=64))
        return
    await db.update_barber_field(message.from_user.id, "name", name)  # type: ignore[union-attr]
    await send_main_menu(message, state, text=MSG["barber_updated"])


# ── Edit bio ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:edit_bio")
async def barber_edit_bio_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    await state.set_state(BarberEditFSM.bio)
    await delete_message_safe(callback.message)
    await callback.message.answer(MSG["barber_enter_bio"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())  # type: ignore[union-attr]


@router.message(BarberEditFSM.bio)
async def barber_edit_bio_done(message: Message, state: FSMContext) -> None:
    bio = parse_text(message, max_len=500)
    if bio is None:
        await message.answer(MSG["invalid_text"].format(max=500))
        return
    await db.update_barber_field(message.from_user.id, "bio", bio)  # type: ignore[union-attr]
    await send_main_menu(message, state, text=MSG["barber_updated"])


# ── Edit segment ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:edit_segment")
async def barber_edit_segment_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    await state.set_state(BarberEditFSM.segment)
    await send_menu_message(
        callback,
        state,
        MSG["barber_enter_segment"],
        reply_markup=segments_kb(),
    )


@router.callback_query(BarberEditFSM.segment, F.data.startswith("seg:"))
async def barber_edit_segment_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    segment = callback.data.split(":")[1]  # type: ignore[union-attr]
    await db.update_barber_field(callback.from_user.id, "segment", segment)  # type: ignore[union-attr]
    await send_main_menu(callback, state, text=MSG["barber_updated"])


# ── Service prices ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:prices")
async def barber_prices_view(callback: CallbackQuery, state: FSMContext) -> None:
    """Show list of services with barber-specific prices."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    uid = callback.from_user.id if callback.from_user else 0
    services = await db.get_services()
    barber_prices: dict[int, float | None] = {}
    for svc in services:
        p = await db.get_barber_service_price(uid, svc["name"])
        barber_prices[svc["id"]] = p
    await send_menu_message(
        callback,
        state,
        "<b>Your Service Prices:</b>\nTap a service to edit its price:",
        reply_markup=barber_prices_kb(services, barber_prices),
    )


@router.callback_query(F.data.startswith("barber_price:"))
async def barber_price_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    _, svc_id_str, svc_name = callback.data.split(":", 2)  # type: ignore[union-attr]
    svc_id = int(svc_id_str)
    await state.set_state(BarberEditFSM.service_price)
    await state.update_data(editing_service_id=svc_id, editing_service_name=svc_name)
    await delete_message_safe(callback.message)
    await callback.message.answer(  # type: ignore[union-attr]
        MSG["barber_enter_price"].format(service=escape(svc_name)),
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_kb(),
    )


@router.message(BarberEditFSM.service_price)
async def barber_price_edit_done(message: Message, state: FSMContext) -> None:
    price = parse_price(message)
    if price is None:
        await message.answer(MSG["invalid_price"])
        return
    data = await state.get_data()
    await db.set_barber_service_price(message.from_user.id, data["editing_service_id"], price)  # type: ignore[union-attr]
    await send_main_menu(message, state, text=MSG["barber_price_updated"])


# ── Incoming bookings ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:incoming")
async def barber_incoming_bookings(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    uid = callback.from_user.id if callback.from_user else 0
    bookings = await db.get_barber_bookings(uid, active_only=True)
    if not bookings:
        await send_main_menu(callback, state, text=MSG["no_incoming"])
        return
    await send_menu_message(
        callback,
        state,
        MSG["incoming_list"],
        reply_markup=barber_incoming_kb(bookings),
    )


@router.callback_query(F.data.startswith("bbk_view:"))
async def barber_view_booking(callback: CallbackQuery, state: FSMContext) -> None:
    booking = await _barber_booking(
        callback, state, ("pending", "confirmed", "declined", "cancelled", "done", "expired")
    )
    if not booking:
        return
    card = format_booking_card(row_to_dict(booking))
    await send_menu_message(
        callback,
        state,
        card,
        reply_markup=barber_booking_actions_kb(booking["id"], booking["status"]),
    )


@router.callback_query(F.data.startswith("bbk_confirm:"))
async def barber_confirm_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await _set_booking_status(
        callback, state, ("pending",), "confirmed", "notify_client_confirmed", "Booking confirmed."
    )


@router.callback_query(F.data.startswith("bbk_decline:"))
async def barber_decline_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await _set_booking_status(
        callback, state, ("pending", "confirmed"), "declined", "notify_client_declined", "Booking declined."
    )


@router.callback_query(F.data.startswith("bbk_done:"))
async def barber_mark_done(callback: CallbackQuery, state: FSMContext) -> None:
    await _set_booking_status(
        callback, state, ("confirmed",), "done", "notify_client_done", "Booking marked as completed."
    )


# ── Barber changes service on a booking ──────────────────────────────────────

@router.callback_query(F.data.startswith("bbk_change_svc:"))
async def barber_change_svc_start(callback: CallbackQuery, state: FSMContext) -> None:
    booking = await _barber_booking(callback, state, ("pending", "confirmed"))
    if not booking:
        return
    services = await db.get_services()
    await send_menu_message(
        callback,
        state,
        MSG["barber_pick_service"],
        reply_markup=barber_service_pick_kb(booking["id"], services),
    )


@router.callback_query(F.data.startswith("bbk_svc:"))
async def barber_change_svc_done(callback: CallbackQuery, state: FSMContext) -> None:
    booking = await _barber_booking(callback, state, ("pending", "confirmed"))
    if not booking:
        return
    service_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    service = await db.get_service_by_id(service_id)
    if not service:
        await send_main_menu(callback, state, text=MSG["error"])
        return
    price = await db.get_effective_price(booking["barber_id"], service_id)
    await db.update_booking_field(booking["id"], "service_id", service_id)
    await db.update_booking_field(booking["id"], "service_name", service["name"])
    if price is not None:
        await db.update_booking_field(booking["id"], "price", price)
    await _notify_client_updated(callback, booking["id"])
    await send_main_menu(callback, state, text=MSG["updated_ok"])


# ── Barber changes price on a booking ────────────────────────────────────────

@router.callback_query(F.data.startswith("bbk_change_price:"))
async def barber_change_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    booking = await _barber_booking(callback, state, ("pending", "confirmed"))
    if not booking:
        return
    booking_id = booking["id"]
    await state.set_state(BarberEditFSM.change_price)
    await state.update_data(editing_booking_id=booking_id)
    await delete_message_safe(callback.message)
    await callback.message.answer(MSG["barber_enter_price_booking"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())  # type: ignore[union-attr]


@router.message(BarberEditFSM.change_price)
async def barber_change_price_done(message: Message, state: FSMContext) -> None:
    price = parse_price(message)
    if price is None:
        await message.answer(MSG["invalid_price"])
        return
    data = await state.get_data()
    booking_id: int = data["editing_booking_id"]
    booking = await db.get_booking(booking_id)
    if (
        not booking
        or booking["barber_id"] != message.from_user.id  # type: ignore[union-attr]
        or booking["status"] not in ("pending", "confirmed")
    ):
        await send_main_menu(message, state, text=MSG["booking_not_editable"])
        return
    await db.update_booking_field(booking_id, "price", price)
    await _notify_client_updated(message, booking_id)
    await send_main_menu(message, state, text=MSG["updated_ok"])


# ── Schedule management ───────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:schedule")
async def barber_schedule_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Enter step 1 of schedule editing — picking weekdays."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    uid = callback.from_user.id if callback.from_user else 0
    current_days = await db.get_barber_weekdays(uid)
    await state.set_state(BarberScheduleFSM.days)
    await state.update_data(selected_days=current_days)
    await send_menu_message(
        callback,
        state,
        MSG["schedule_days"],
        reply_markup=schedule_days_kb(current_days),
    )


@router.callback_query(BarberScheduleFSM.days, F.data.startswith("sched_day:"))
async def schedule_toggle_day(callback: CallbackQuery, state: FSMContext) -> None:
    """Toggle a weekday on/off."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    day = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    data = await state.get_data()
    selected: list[int] = list(data.get("selected_days", []))
    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
    await state.update_data(selected_days=selected)
    try:
        await callback.message.edit_reply_markup(reply_markup=schedule_days_kb(selected))  # type: ignore[union-attr]
    except Exception:
        pass


@router.callback_query(BarberScheduleFSM.days, F.data == "sched_save")
async def schedule_save_days(callback: CallbackQuery, state: FSMContext) -> None:
    """Save chosen weekdays and proceed to slot selection."""
    if not await _active_barber(callback, state):
        return
    uid = callback.from_user.id if callback.from_user else 0
    data = await state.get_data()
    selected_days: list[int] = sorted(data.get("selected_days", []))
    if not selected_days:
        # An empty schedule would silently fall back to the Mon–Sat default
        await safe_answer(callback, MSG["schedule_need_day"], show_alert=True)
        return
    conflicts = [
        bk for bk in await db.get_upcoming_active_bookings(uid)
        if _slot_weekday(bk["slot_datetime"]) not in selected_days
    ]
    if conflicts:
        await safe_answer(callback, _conflict_text(conflicts), show_alert=True)
        return
    await safe_answer(callback)
    await db.set_barber_weekdays(uid, selected_days)

    # Move to step 2 — time slots
    current_slots = await db.get_barber_time_slots(uid)
    await state.set_state(BarberScheduleFSM.slots)
    await state.update_data(selected_slots=current_slots)
    await send_menu_message(
        callback,
        state,
        MSG["schedule_slots"],
        reply_markup=schedule_slots_kb(current_slots),
    )


@router.callback_query(BarberScheduleFSM.slots, F.data.startswith("sched_slot:"))
async def schedule_toggle_slot(callback: CallbackQuery, state: FSMContext) -> None:
    """Toggle a time slot on/off."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    slot = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    data = await state.get_data()
    selected: list[str] = list(data.get("selected_slots", []))
    if slot in selected:
        selected.remove(slot)
    else:
        selected.append(slot)
    selected.sort()
    await state.update_data(selected_slots=selected)
    try:
        await callback.message.edit_reply_markup(reply_markup=schedule_slots_kb(selected))  # type: ignore[union-attr]
    except Exception:
        pass


@router.callback_query(BarberScheduleFSM.slots, F.data == "sched_slot_save")
async def schedule_save_slots(callback: CallbackQuery, state: FSMContext) -> None:
    """Save time slots and finish schedule editing."""
    if not await _active_barber(callback, state):
        return
    uid = callback.from_user.id if callback.from_user else 0
    data = await state.get_data()
    selected_slots: list[str] = data.get("selected_slots", [])
    if not selected_slots:
        await safe_answer(callback, MSG["schedule_need_slot"], show_alert=True)
        return
    conflicts = [
        bk for bk in await db.get_upcoming_active_bookings(uid)
        if bk["slot_datetime"].split(" ")[1] not in selected_slots
    ]
    if conflicts:
        await safe_answer(callback, _conflict_text(conflicts), show_alert=True)
        return
    await safe_answer(callback)
    await db.set_barber_time_slots(uid, selected_slots)
    await send_main_menu(callback, state, text=MSG["schedule_saved"])


# ── Days off ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:days_off")
async def barber_days_off_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Show the 30-day days-off picker."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    uid = callback.from_user.id if callback.from_user else 0
    days_off = await db.get_barber_days_off(uid)
    await state.set_state(BarberDaysOffFSM.picking)
    await send_menu_message(
        callback,
        state,
        MSG["days_off_pick"],
        reply_markup=days_off_kb(days_off),
    )


@router.callback_query(BarberDaysOffFSM.picking, F.data.startswith("doff:"))
async def days_off_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    """Toggle a day-off date in-place."""
    if not await _active_barber(callback, state):
        return
    date_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    uid = callback.from_user.id if callback.from_user else 0
    if date_str not in await db.get_barber_days_off(uid):
        busy = await db.get_active_bookings_on(uid, date_str)
        if busy:
            await safe_answer(callback, MSG["days_off_has_bookings"].format(n=len(busy)), show_alert=True)
            return
    await safe_answer(callback)
    await db.toggle_day_off(uid, date_str)
    days_off = await db.get_barber_days_off(uid)
    try:
        await callback.message.edit_reply_markup(reply_markup=days_off_kb(days_off))  # type: ignore[union-attr]
    except Exception:
        pass


@router.callback_query(BarberDaysOffFSM.picking, F.data == "doff_done")
async def days_off_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Close the days-off picker and return to main menu."""
    await safe_answer(callback)
    await send_main_menu(callback, state, text=MSG["days_off_saved"])


# ── Leave barbershop ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "barber:leave")
async def barber_leave_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask the barber to confirm leaving."""
    if not await _active_barber(callback, state):
        return
    await safe_answer(callback)
    await send_menu_message(
        callback,
        state,
        MSG["leave_confirm"],
        reply_markup=leave_confirm_kb(),
    )


@router.callback_query(F.data == "leave_yes")
async def barber_leave_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    """Process the barber leaving the barbershop."""
    barber = await _active_barber(callback, state)
    if not barber:
        return
    await safe_answer(callback)
    uid = callback.from_user.id
    for bk in await db.cancel_active_barber_bookings(uid):
        await _notify(callback, bk["client_id"], MSG["notify_client_barber_left"].format(id=bk["id"]))
    await db.delete_barber(uid)
    await _notify(
        callback,
        settings.admin_id,
        MSG["notify_admin_left"].format(name=escape(barber["name"]), id=uid),
    )
    await send_main_menu(callback, state, text=MSG["leave_done"])


@router.callback_query(F.data == "leave_no")
async def barber_leave_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    await send_main_menu(callback, state, text=MSG["leave_cancelled"])
