"""Booking flow handler — client-side booking and booking management."""
from __future__ import annotations

import datetime
import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import db
from app.formatters import format_booking_card
from app.keyboards import (
    barber_booking_actions_kb,
    barbers_kb,
    booking_confirm_kb,
    cancel_kb,
    client_booking_actions_kb,
    dates_kb,
    my_bookings_kb,
    services_kb,
    slots_kb,
)
from app.states import BookingFSM
from app.texts import BTN, MSG
from app.utils import (
    delete_message_safe,
    delete_previous_menu,
    parse_phone,
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
router = Router(name="booking")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _booking_card(booking) -> str:
    """Booking card with the barber's name filled in."""
    barber = await db.get_barber(booking["barber_id"])
    barber_name = barber["name"] if barber else "—"
    return format_booking_card({**row_to_dict(booking), "barber_name": barber_name})


async def _notify(callback_or_message, chat_id: int, text: str, **kwargs) -> None:
    """Send a notification, logging (not raising) on failure."""
    try:
        await callback_or_message.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, **kwargs
        )
    except Exception as e:
        logger.warning("Could not notify %s: %s", chat_id, e)


async def _own_pending_booking(user_id: int, booking_id: int):
    """Return the booking if it belongs to the user and is still pending, else None."""
    booking = await db.get_booking(booking_id)
    if not booking or booking["client_id"] != user_id or booking["status"] != "pending":
        return None
    return booking


async def _notify_barber_updated(event, booking_id: int) -> None:
    booking = await db.get_booking(booking_id)
    if booking:
        await _notify(
            event,
            booking["barber_id"],
            MSG["notify_barber_updated"].format(card=await _booking_card(booking)),
        )


async def _show_slots(callback: CallbackQuery, state: FSMContext, text: str) -> bool:
    """Show free slots for the selected date. Returns False if none are left."""
    data = await state.get_data()
    selected_date = datetime.date.fromisoformat(data["selected_date"])
    available_slots = await db.get_free_slots(data["barber_id"], selected_date)
    if not available_slots:
        return False
    await state.set_state(BookingFSM.time_slot)
    await send_menu_message(callback, state, text, reply_markup=slots_kb(available_slots))
    return True


# ─────────────────────────────────────────────────────────────────────────────
# START BOOKING FLOW
# ─────────────────────────────────────────────────────────────────────────────

@router.message(text_is(BTN["book"], "book an appointment", "book", "записаться"), NOT_TYPING)
async def start_booking(message: Message, state: FSMContext) -> None:
    """Begin the booking flow by asking for the client's name."""
    await delete_previous_menu(message, state)
    await state.clear()
    await state.set_state(BookingFSM.name)
    await message.answer(MSG["book_name"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())


@router.message(BookingFSM.name)
async def booking_got_name(message: Message, state: FSMContext) -> None:
    """Store name and ask for phone."""
    name = parse_text(message, min_len=2, max_len=64)
    if name is None:
        await message.answer(MSG["invalid_name"])
        return
    await state.update_data(client_name=name)
    await state.set_state(BookingFSM.phone)
    await message.answer(MSG["book_phone"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())


@router.message(BookingFSM.phone)
async def booking_got_phone(message: Message, state: FSMContext) -> None:
    """Store phone and show service selection."""
    phone = parse_phone(message)
    if phone is None:
        await message.answer(MSG["invalid_phone"])
        return
    await state.update_data(client_phone=phone)
    services = await db.get_services()
    if not services:
        await send_main_menu(message, state, text=MSG["error"])
        return
    await state.set_state(BookingFSM.service)
    await send_menu_message(
        message,
        state,
        MSG["book_service"],
        reply_markup=services_kb(services),
    )


@router.callback_query(BookingFSM.service, F.data.startswith("svc:"))
async def booking_got_service(callback: CallbackQuery, state: FSMContext) -> None:
    """Store service and show barber selection (or update existing if editing)."""
    _, svc_id, svc_name, svc_price = callback.data.split(":", 3)  # type: ignore[union-attr]
    data = await state.get_data()

    if data.get("is_editing") and data.get("editing_booking_id"):
        booking_id = int(data["editing_booking_id"])
        booking = await _own_pending_booking(callback.from_user.id, booking_id)
        if not booking:
            await safe_answer(callback, MSG["booking_not_editable"], show_alert=True)
            await send_main_menu(callback, state, text=MSG["booking_not_editable"])
            return
        await safe_answer(callback)
        price = await db.get_effective_price(booking["barber_id"], int(svc_id))
        await db.update_booking_field(booking_id, "service_id", int(svc_id))
        await db.update_booking_field(booking_id, "service_name", svc_name)
        await db.update_booking_field(booking_id, "price", price if price is not None else float(svc_price))
        await _notify_barber_updated(callback, booking_id)
        await send_main_menu(callback, state, text=MSG["updated_ok"])
        return

    await safe_answer(callback)
    await state.update_data(
        service_id=int(svc_id),
        service_name=svc_name,
        service_price=float(svc_price),
    )
    barbers = await db.get_approved_barbers()
    if not barbers:
        await send_main_menu(callback, state, text=MSG["book_no_barbers"])
        return
    await state.set_state(BookingFSM.barber)
    await send_menu_message(
        callback,
        state,
        MSG["book_barber"],
        reply_markup=barbers_kb(barbers),
    )


@router.callback_query(BookingFSM.barber, F.data.startswith("pick_barber:"))
async def booking_got_barber(callback: CallbackQuery, state: FSMContext) -> None:
    """Store barber and show date selection (or update existing if editing)."""
    barber_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    barber = await db.get_barber(barber_id)
    if not barber or barber["status"] != "approved":
        await safe_answer(callback)
        await send_main_menu(callback, state, text=MSG["error"])
        return

    data = await state.get_data()
    if data.get("is_editing") and data.get("editing_booking_id"):
        booking_id = int(data["editing_booking_id"])
        booking = await _own_pending_booking(callback.from_user.id, booking_id)
        if not booking:
            await safe_answer(callback, MSG["booking_not_editable"], show_alert=True)
            await send_main_menu(callback, state, text=MSG["booking_not_editable"])
            return
        old_barber_id = booking["barber_id"]
        if barber_id == old_barber_id:
            await safe_answer(callback)
            await send_main_menu(callback, state, text=MSG["updated_ok"])
            return
        # The new barber must work at the booked time and have that slot free
        slot = booking["slot_datetime"]
        if slot:
            date_str, slot_time = slot.split(" ")
            free = await db.get_free_slots(barber_id, datetime.date.fromisoformat(date_str))
            if slot_time not in free:
                await safe_answer(callback, MSG["barber_unavailable"], show_alert=True)
                return
        price = await db.get_effective_price(barber_id, booking["service_id"])
        if not await db.reassign_booking(booking_id, barber_id, price):
            await safe_answer(callback, MSG["barber_unavailable"], show_alert=True)
            return
        await safe_answer(callback)
        await _notify(callback, old_barber_id, MSG["notify_barber_reassigned"].format(id=booking_id))
        updated = await db.get_booking(booking_id)
        await _notify(
            callback,
            barber_id,
            MSG["notify_barber_new_booking"].format(card=await _booking_card(updated)),
            reply_markup=barber_booking_actions_kb(booking_id, "pending", with_back=False),
        )
        await send_main_menu(callback, state, text=MSG["updated_ok"])
        return

    await safe_answer(callback)
    # Barber-specific price overrides the studio price
    price = await db.get_effective_price(barber_id, int(data["service_id"]))
    await state.update_data(
        barber_id=barber_id,
        barber_name=barber["name"],
        service_price=price if price is not None else data.get("service_price", 0.0),
    )

    # Only dates that still have at least one free slot
    available_dates = await db.get_available_dates(barber_id, days_ahead=14)
    if not available_dates:
        await send_main_menu(callback, state, text=MSG["book_no_dates"])
        return

    await state.set_state(BookingFSM.date)
    await send_menu_message(
        callback,
        state,
        MSG["book_date"],
        reply_markup=dates_kb(available_dates),
    )


@router.callback_query(BookingFSM.date, F.data.startswith("date:"))
async def booking_got_date(callback: CallbackQuery, state: FSMContext) -> None:
    """Store selected date and show time slot selection."""
    await safe_answer(callback)
    date_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    await state.update_data(selected_date=date_str)
    if not await _show_slots(callback, state, MSG["book_slot"]):
        await send_main_menu(callback, state, text=MSG["book_no_slots"])


@router.callback_query(BookingFSM.time_slot, F.data.startswith("slot:"))
async def booking_got_slot(callback: CallbackQuery, state: FSMContext) -> None:
    """Store selected time slot and show confirmation card."""
    await safe_answer(callback)
    slot_time = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    data = await state.get_data()
    slot_datetime = f"{data['selected_date']} {slot_time}"

    if await db.is_slot_taken(data["barber_id"], slot_datetime):
        if not await _show_slots(callback, state, MSG["slot_taken"]):
            await send_main_menu(callback, state, text=MSG["book_no_slots"])
        return

    await state.update_data(slot_time=slot_time, slot_datetime=slot_datetime)

    # Re-fetch barber name in case it changed
    barber = await db.get_barber(data["barber_id"])
    barber_name = barber["name"] if barber else data.get("barber_name", "—")

    card = format_booking_card({
        "id": "—",
        "client_name": data.get("client_name", "—"),
        "client_phone": data.get("client_phone", "—"),
        "service_name": data.get("service_name", "—"),
        "barber_name": barber_name,
        "price": data.get("service_price", 0),
        "status": "pending",
        "slot_datetime": slot_datetime,
    })

    await state.set_state(BookingFSM.confirm)
    await send_menu_message(
        callback,
        state,
        f"{MSG['book_confirm']}\n\n{card}",
        reply_markup=booking_confirm_kb(),
    )


@router.callback_query(BookingFSM.confirm, F.data == "book_confirm")
async def booking_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    """Save the booking to the database and notify the barber."""
    await safe_answer(callback)
    data = await state.get_data()
    # Leave the confirm state right away so a double tap cannot create two bookings
    await state.set_state(None)

    barber = await db.get_barber(data["barber_id"])
    if not barber or barber["status"] != "approved":
        await send_main_menu(callback, state, text=MSG["book_no_barbers"])
        return

    if await db.is_slot_taken(data["barber_id"], data["slot_datetime"]):
        await state.set_data(data)
        if not await _show_slots(callback, state, MSG["slot_taken"]):
            await send_main_menu(callback, state, text=MSG["book_no_slots"])
        return

    booking_id = await db.create_booking(
        client_id=callback.from_user.id,  # type: ignore[union-attr]
        barber_id=data["barber_id"],
        client_name=data["client_name"],
        client_phone=data["client_phone"],
        service_name=data["service_name"],
        price=data.get("service_price", 0.0),
        slot_datetime=data["slot_datetime"],
        service_id=data.get("service_id"),
    )
    if booking_id is None:
        # Another client took the slot between the check and the insert
        await state.set_data(data)
        if not await _show_slots(callback, state, MSG["slot_taken"]):
            await send_main_menu(callback, state, text=MSG["book_no_slots"])
        return

    booking = await db.get_booking(booking_id)
    card = await _booking_card(booking)
    await _notify(
        callback,
        data["barber_id"],
        MSG["notify_barber_new_booking"].format(card=card),
        reply_markup=barber_booking_actions_kb(booking_id, "pending", with_back=False),
    )

    await send_main_menu(callback, state, text=MSG["book_ok"])


@router.callback_query(BookingFSM.confirm, F.data == "book_cancel")
async def booking_cancelled_at_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel booking at the confirm step."""
    await safe_answer(callback)
    await send_main_menu(callback, state, text=MSG["cancelled"])


# ─────────────────────────────────────────────────────────────────────────────
# MY BOOKINGS
# ─────────────────────────────────────────────────────────────────────────────

@router.message(text_is(BTN["my_bookings"], "my bookings", "bookings", "мои заявки"), NOT_TYPING)
async def handle_my_bookings(message: Message, state: FSMContext) -> None:
    """Show a list of the client's own bookings."""
    await delete_previous_menu(message, state)
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    bookings = await db.get_client_bookings(uid)
    if not bookings:
        await message.answer(MSG["my_bookings_empty"], parse_mode=ParseMode.HTML)
        return
    await send_menu_message(
        message,
        state,
        MSG["my_bookings_list"],
        reply_markup=my_bookings_kb(bookings),
    )


@router.callback_query(F.data.startswith("mybk:"))
async def view_my_booking(callback: CallbackQuery, state: FSMContext) -> None:
    """Show details for one of the client's bookings."""
    await safe_answer(callback)
    booking_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    booking = await db.get_booking(booking_id)
    if not booking or booking["client_id"] != callback.from_user.id:
        await send_main_menu(callback, state, text=MSG["error"])
        return

    card = await _booking_card(booking)
    is_pending = booking["status"] == "pending"

    await send_menu_message(
        callback,
        state,
        card,
        reply_markup=client_booking_actions_kb(booking_id, is_pending),
    )


@router.callback_query(F.data == "mybk_back")
async def my_bookings_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to the My Bookings list."""
    await safe_answer(callback)
    uid = callback.from_user.id if callback.from_user else 0
    bookings = await db.get_client_bookings(uid)
    if not bookings:
        await send_main_menu(callback, state, text=MSG["my_bookings_empty"])
        return
    await send_menu_message(
        callback,
        state,
        MSG["my_bookings_list"],
        reply_markup=my_bookings_kb(bookings),
    )


# ── Client booking edits ──────────────────────────────────────────────────────

async def _start_client_edit(callback: CallbackQuery, state: FSMContext) -> int | None:
    """Validate a client edit button; returns the booking id or None (already answered)."""
    booking_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    if not await _own_pending_booking(callback.from_user.id, booking_id):
        await safe_answer(callback, MSG["booking_not_editable"], show_alert=True)
        await delete_message_safe(callback.message)
        return None
    await safe_answer(callback)
    await state.clear()
    await state.update_data(editing_booking_id=booking_id)
    return booking_id


@router.callback_query(F.data.startswith("cbk_edit_name:"))
async def client_edit_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await _start_client_edit(callback, state) is None:
        return
    await state.set_state(BookingFSM.edit_name)
    await delete_message_safe(callback.message)
    await callback.message.answer(MSG["enter_new_name"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())  # type: ignore[union-attr]


@router.message(BookingFSM.edit_name)
async def client_edit_name_done(message: Message, state: FSMContext) -> None:
    name = parse_text(message, min_len=2, max_len=64)
    if name is None:
        await message.answer(MSG["invalid_name"])
        return
    data = await state.get_data()
    booking_id: int = data["editing_booking_id"]
    if not await _own_pending_booking(message.from_user.id, booking_id):  # type: ignore[union-attr]
        await send_main_menu(message, state, text=MSG["booking_not_editable"])
        return
    await db.update_booking_field(booking_id, "client_name", name)
    await _notify_barber_updated(message, booking_id)
    await send_main_menu(message, state, text=MSG["updated_ok"])


@router.callback_query(F.data.startswith("cbk_edit_phone:"))
async def client_edit_phone_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await _start_client_edit(callback, state) is None:
        return
    await state.set_state(BookingFSM.edit_phone)
    await delete_message_safe(callback.message)
    await callback.message.answer(MSG["enter_new_phone"], parse_mode=ParseMode.HTML, reply_markup=cancel_kb())  # type: ignore[union-attr]


@router.message(BookingFSM.edit_phone)
async def client_edit_phone_done(message: Message, state: FSMContext) -> None:
    phone = parse_phone(message)
    if phone is None:
        await message.answer(MSG["invalid_phone"])
        return
    data = await state.get_data()
    booking_id: int = data["editing_booking_id"]
    if not await _own_pending_booking(message.from_user.id, booking_id):  # type: ignore[union-attr]
        await send_main_menu(message, state, text=MSG["booking_not_editable"])
        return
    await db.update_booking_field(booking_id, "client_phone", phone)
    await _notify_barber_updated(message, booking_id)
    await send_main_menu(message, state, text=MSG["updated_ok"])


@router.callback_query(F.data.startswith("cbk_change_svc:"))
async def client_change_service(callback: CallbackQuery, state: FSMContext) -> None:
    """Let a client change the service on a pending booking."""
    if await _start_client_edit(callback, state) is None:
        return
    services = await db.get_services()
    await state.set_state(BookingFSM.service)
    await state.update_data(is_editing=True)
    await send_menu_message(
        callback,
        state,
        MSG["book_service"],
        reply_markup=services_kb(services),
    )


@router.callback_query(F.data.startswith("cbk_change_barber:"))
async def client_change_barber(callback: CallbackQuery, state: FSMContext) -> None:
    """Let a client change the barber on a pending booking."""
    if await _start_client_edit(callback, state) is None:
        return
    barbers = await db.get_approved_barbers()
    if not barbers:
        await send_main_menu(callback, state, text=MSG["book_no_barbers"])
        return
    await state.set_state(BookingFSM.barber)
    await state.update_data(is_editing=True)
    await send_menu_message(
        callback,
        state,
        MSG["book_barber"],
        reply_markup=barbers_kb(barbers),
    )


@router.callback_query(F.data.startswith("cbk_cancel:"))
async def client_cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel a client's pending booking."""
    booking_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    booking = await _own_pending_booking(callback.from_user.id, booking_id)
    if not booking:
        await safe_answer(callback, MSG["booking_not_editable"], show_alert=True)
        await delete_message_safe(callback.message)
        return
    await safe_answer(callback)
    await db.update_booking_status(booking_id, "cancelled")
    await _notify(callback, booking["barber_id"], MSG["notify_barber_cancelled"].format(id=booking_id))
    await send_main_menu(callback, state, text=MSG["booking_cancelled_ok"])
