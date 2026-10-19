"""All keyboards — reply and inline — for the bot."""
from __future__ import annotations

import datetime

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.config import local_today
from app.texts import BTN, WEEKDAY_NAMES, WEEKDAY_SHORT, TIME_SLOTS, MAPS_URL

__all__ = [
    "remove_kb",
    "main_menu_kb",
    "cancel_kb",
    "location_kb",
    "services_kb",
    "barbers_kb",
    "dates_kb",
    "slots_kb",
    "booking_confirm_kb",
    "my_bookings_kb",
    "client_booking_actions_kb",
    "barber_studio_kb",
    "barber_booking_actions_kb",
    "barber_profile_kb",
    "schedule_days_kb",
    "schedule_slots_kb",
    "days_off_kb",
    "leave_confirm_kb",
    "admin_panel_kb",
    "admin_barber_actions_kb",
    "admin_barber_list_kb",
    "admin_bookings_kb",
    "admin_services_kb",
    "segments_kb",
    "barber_service_pick_kb",
    "yes_no_kb",
]

# ── Row helper ────────────────────────────────────────────────────────────────
def _row_val(row, key: str, default="") -> str:
    if isinstance(row, dict):
        return str(row.get(key, default) or default)
    try:
        val = row[key]
        return str(val if val is not None else default)
    except Exception:
        return str(default)


# ── Sentinel ──────────────────────────────────────────────────────────────────
remove_kb = ReplyKeyboardRemove()


# ── Main menu ─────────────────────────────────────────────────────────────────

def main_menu_kb(
    *,
    is_admin: bool = False,
    barber_status: str | None = None,
) -> ReplyKeyboardMarkup:
    """
    Build the main reply keyboard. Shows/hides rows based on user role.

    barber_status: None | 'pending' | 'approved' | 'rejected' | 'left'
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN["book"])
    builder.button(text=BTN["my_bookings"])
    builder.button(text=BTN["location"])

    if barber_status == "approved":
        builder.button(text=BTN["barber_studio"])
    elif barber_status == "pending":
        builder.button(text=BTN["app_status"])
    elif barber_status in (None, "rejected", "left"):
        builder.button(text=BTN["become_barber"])

    if is_admin:
        builder.button(text=BTN["admin_panel"])

    builder.button(text=BTN["cancel"])
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    """Single-button cancel keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN["cancel"])
    return builder.as_markup(resize_keyboard=True)


# ── Location ──────────────────────────────────────────────────────────────────

def location_kb() -> InlineKeyboardMarkup:
    """Inline keyboard with a Google Maps URL button."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["open_maps"], url=MAPS_URL)
    ]])


# ── Booking flow ──────────────────────────────────────────────────────────────

def services_kb(services: list) -> InlineKeyboardMarkup:
    """Inline keyboard listing available services."""
    builder = InlineKeyboardBuilder()
    for svc in services:
        label = f"{svc['name']} — ${svc['price']:.0f}"
        builder.button(text=label, callback_data=f"svc:{svc['id']}:{svc['name']}:{svc['price']:.0f}")
    builder.adjust(1)
    return builder.as_markup()


def barbers_kb(barbers: list) -> InlineKeyboardMarkup:
    """Inline keyboard listing approved barbers."""
    builder = InlineKeyboardBuilder()
    for b in barbers:
        segment = (b["segment"] or "standard").capitalize()
        rating = b["rating"] or 5.0
        label = f"{b['name']} | {segment} | Rating: {rating}"
        builder.button(text=label, callback_data=f"pick_barber:{b['user_id']}")
    builder.adjust(1)
    return builder.as_markup()


def dates_kb(dates: list[datetime.date]) -> InlineKeyboardMarkup:
    """Inline keyboard with available booking dates."""
    builder = InlineKeyboardBuilder()
    for d in dates:
        weekday = WEEKDAY_SHORT[d.weekday()]
        label = f"{weekday}, {d.strftime('%b %d')}"
        builder.button(text=label, callback_data=f"date:{d.isoformat()}")
    builder.adjust(3)
    return builder.as_markup()


def slots_kb(available_slots: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard with available time slots."""
    builder = InlineKeyboardBuilder()
    for slot in available_slots:
        # Convert 24h to 12h for display
        try:
            dt = datetime.datetime.strptime(slot, "%H:%M")
            label = dt.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            label = slot
        builder.button(text=label, callback_data=f"slot:{slot}")
    builder.adjust(3)
    return builder.as_markup()


def booking_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm / cancel inline keyboard for booking confirmation step."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["confirm"], callback_data="book_confirm"),
        InlineKeyboardButton(text=BTN["cancel"], callback_data="book_cancel"),
    ]])


# ── My Bookings ───────────────────────────────────────────────────────────────

def my_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    """Inline keyboard listing the client's bookings."""
    builder = InlineKeyboardBuilder()
    for bk in bookings:
        status = _row_val(bk, "status")
        status_tag = f"[{status.upper()}]" if status else ""
        svc_name = _row_val(bk, "service_name", "N/A")
        bk_id = _row_val(bk, "id")
        label = f"#{bk_id} {status_tag} - {svc_name}"
        builder.button(text=label, callback_data=f"mybk:{bk_id}")
    builder.adjust(1)
    return builder.as_markup()


def client_booking_actions_kb(booking_id: int, is_pending: bool) -> InlineKeyboardMarkup:
    """Action buttons shown to a client when viewing a single booking."""
    builder = InlineKeyboardBuilder()
    if is_pending:
        builder.button(text=BTN["edit_name"], callback_data=f"cbk_edit_name:{booking_id}")
        builder.button(text=BTN["edit_phone"], callback_data=f"cbk_edit_phone:{booking_id}")
        builder.button(text=BTN["change_service"], callback_data=f"cbk_change_svc:{booking_id}")
        builder.button(text=BTN["change_barber"], callback_data=f"cbk_change_barber:{booking_id}")
        builder.button(text=BTN["cancel_booking"], callback_data=f"cbk_cancel:{booking_id}")
    builder.button(text=BTN["back"], callback_data="mybk_back")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


# ── Barber Studio ─────────────────────────────────────────────────────────────

def barber_studio_kb() -> InlineKeyboardMarkup:
    """Main inline keyboard for the barber cabinet."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN["incoming_bookings"], callback_data="barber:incoming")
    builder.button(text=BTN["my_profile"], callback_data="barber:profile")
    builder.button(text=BTN["edit_barber_name"], callback_data="barber:edit_name")
    builder.button(text=BTN["edit_bio"], callback_data="barber:edit_bio")
    builder.button(text=BTN["edit_segment"], callback_data="barber:edit_segment")
    builder.button(text=BTN["service_prices"], callback_data="barber:prices")
    builder.button(text=BTN["my_schedule"], callback_data="barber:schedule")
    builder.button(text=BTN["days_off"], callback_data="barber:days_off")
    builder.button(text=BTN["leave_barbershop"], callback_data="barber:leave")
    builder.adjust(1, 2, 2, 1, 2, 1)
    return builder.as_markup()


def barber_profile_kb() -> InlineKeyboardMarkup:
    """Back button from profile view."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["back"], callback_data="barber:studio")
    ]])


def barber_booking_actions_kb(
    booking_id: int, status: str = "pending", with_back: bool = True
) -> InlineKeyboardMarkup:
    """Action buttons for a barber managing a booking; only valid actions for its status."""
    builder = InlineKeyboardBuilder()
    sizes: list[int] = []
    if status == "pending":
        builder.button(text=BTN["confirm_booking"], callback_data=f"bbk_confirm:{booking_id}")
        builder.button(text=BTN["decline_booking"], callback_data=f"bbk_decline:{booking_id}")
        sizes.append(2)
    elif status == "confirmed":
        builder.button(text=BTN["mark_done"], callback_data=f"bbk_done:{booking_id}")
        builder.button(text=BTN["decline_booking"], callback_data=f"bbk_decline:{booking_id}")
        sizes.append(2)
    if status in ("pending", "confirmed"):
        builder.button(text=BTN["change_service_barber"], callback_data=f"bbk_change_svc:{booking_id}")
        builder.button(text=BTN["change_price_barber"], callback_data=f"bbk_change_price:{booking_id}")
        sizes.append(2)
    if with_back:
        builder.button(text=BTN["back"], callback_data="barber:incoming")
        sizes.append(1)
    builder.adjust(*sizes)
    return builder.as_markup()


def barber_service_pick_kb(booking_id: int, services: list) -> InlineKeyboardMarkup:
    """Service list for a barber changing the service on a booking."""
    builder = InlineKeyboardBuilder()
    for svc in services:
        builder.button(text=svc["name"], callback_data=f"bbk_svc:{booking_id}:{svc['id']}")
    builder.button(text=BTN["back"], callback_data=f"bbk_view:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


# ── Barber incoming list ───────────────────────────────────────────────────────

def barber_incoming_kb(bookings: list) -> InlineKeyboardMarkup:
    """Inline keyboard listing a barber's incoming bookings."""
    builder = InlineKeyboardBuilder()
    for bk in bookings:
        status = _row_val(bk, "status")
        status_tag = f"[{status.upper()}]" if status else ""
        c_name = _row_val(bk, "client_name", "Client")
        s_name = _row_val(bk, "service_name", "N/A")
        bk_id = _row_val(bk, "id")
        label = f"#{bk_id} {status_tag} - {c_name} | {s_name}"
        builder.button(text=label, callback_data=f"bbk_view:{bk_id}")
    builder.button(text=BTN["back"], callback_data="barber:studio")
    builder.adjust(1)
    return builder.as_markup()


# ── Barber service prices ─────────────────────────────────────────────────────

def barber_prices_kb(services: list, barber_prices: dict[int, float | None]) -> InlineKeyboardMarkup:
    """Inline keyboard for editing barber-specific service prices."""
    builder = InlineKeyboardBuilder()
    for svc in services:
        price = barber_prices.get(svc["id"]) or svc["price"]
        label = f"{svc['name']} — ${price:.0f}"
        builder.button(text=label, callback_data=f"barber_price:{svc['id']}:{svc['name']}")
    builder.button(text=BTN["back"], callback_data="barber:studio")
    builder.adjust(1)
    return builder.as_markup()


# ── Schedule ──────────────────────────────────────────────────────────────────

def schedule_days_kb(selected_days: list[int]) -> InlineKeyboardMarkup:
    """Inline keyboard for selecting work weekdays."""
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(WEEKDAY_NAMES):
        mark = "[x]" if i in selected_days else "[ ]"
        builder.button(text=f"{mark} {name}", callback_data=f"sched_day:{i}")
    builder.button(text=BTN["save_days"], callback_data="sched_save")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def schedule_slots_kb(selected_slots: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard for selecting time slots."""
    builder = InlineKeyboardBuilder()
    for slot in TIME_SLOTS:
        mark = "[x]" if slot in selected_slots else "[ ]"
        try:
            dt = datetime.datetime.strptime(slot, "%H:%M")
            display = dt.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            display = slot
        builder.button(text=f"{mark} {display}", callback_data=f"sched_slot:{slot}")
    builder.button(text=BTN["save_slots"], callback_data="sched_slot_save")
    builder.adjust(3, 3, 3, 2, 1)
    return builder.as_markup()


# ── Days off ──────────────────────────────────────────────────────────────────

def days_off_kb(days_off: list[str], days_ahead: int = 30) -> InlineKeyboardMarkup:
    """
    Inline keyboard showing the next `days_ahead` dates.
    Dates in `days_off` show [OFF].
    """
    builder = InlineKeyboardBuilder()
    today = local_today()
    for offset in range(0, days_ahead):  # today is bookable, so it must be markable too
        candidate = today + datetime.timedelta(days=offset)
        date_str = candidate.isoformat()
        prefix = "[OFF] " if date_str in days_off else ""
        weekday = WEEKDAY_SHORT[candidate.weekday()]
        label = f"{prefix}{weekday} {candidate.strftime('%b %d')}"
        builder.button(text=label, callback_data=f"doff:{date_str}")
    builder.button(text=BTN["done"], callback_data="doff_done")
    builder.adjust(3)
    return builder.as_markup()


# ── Leave barbershop ──────────────────────────────────────────────────────────

def leave_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm/cancel keyboard for leaving the barbershop."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["yes_leave"], callback_data="leave_yes"),
        InlineKeyboardButton(text=BTN["cancel"], callback_data="leave_no"),
    ]])


# ── Admin panel ───────────────────────────────────────────────────────────────

def admin_panel_kb() -> InlineKeyboardMarkup:
    """Main admin panel inline keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN["pending_apps"], callback_data="admin:pending")
    builder.button(text=BTN["all_barbers"], callback_data="admin:barbers")
    builder.button(text=BTN["all_bookings"], callback_data="admin:bookings")
    builder.button(text=BTN["studio_prices"], callback_data="admin:prices")
    builder.adjust(1)
    return builder.as_markup()


def admin_barber_actions_kb(
    barber_user_id: int,
    status: str,
    back_cb: str = "admin:panel",
) -> InlineKeyboardMarkup:
    """Approve/reject buttons for a pending barber application."""
    builder = InlineKeyboardBuilder()
    sizes: list[int] = []
    if status == "pending":
        builder.button(
            text=BTN["admin_approve"],
            callback_data=f"admin_approve:{barber_user_id}",
        )
        builder.button(
            text=BTN["admin_reject"],
            callback_data=f"admin_reject:{barber_user_id}",
        )
        sizes.append(2)
    elif status == "approved":
        builder.button(text=BTN["admin_set_rating"], callback_data=f"admin_rating:{barber_user_id}")
        builder.button(text=BTN["admin_remove"], callback_data=f"admin_remove:{barber_user_id}")
        sizes.append(2)
    builder.button(text=BTN["back"], callback_data=back_cb)
    sizes.append(1)
    builder.adjust(*sizes)
    return builder.as_markup()


def admin_barber_list_kb(barbers: list) -> InlineKeyboardMarkup:
    """List of all barbers for the admin."""
    builder = InlineKeyboardBuilder()
    for b in barbers:
        status = _row_val(b, "status")
        status_tag = f"[{status.upper()}]" if status else ""
        name = _row_val(b, "name", "Barber")
        uid = _row_val(b, "user_id")
        label = f"{name} {status_tag}".strip()
        builder.button(text=label, callback_data=f"admin_barber:{uid}")
    builder.button(text=BTN["back"], callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def admin_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    """List of all bookings for the admin."""
    builder = InlineKeyboardBuilder()
    for bk in bookings[:20]:  # cap at 20 to avoid huge keyboards
        status = _row_val(bk, "status")
        status_tag = f"[{status.upper()}]" if status else ""
        c_name = _row_val(bk, "client_name", "Client")
        bk_id = _row_val(bk, "id")
        label = f"#{bk_id} {status_tag} - {c_name}"
        builder.button(text=label, callback_data=f"admin_bk:{bk_id}")
    builder.button(text=BTN["back"], callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def admin_services_kb(services: list) -> InlineKeyboardMarkup:
    """List of services for price editing."""
    builder = InlineKeyboardBuilder()
    for svc in services:
        label = f"{svc['name']} — ${svc['price']:.0f}"
        builder.button(text=label, callback_data=f"admin_svc:{svc['id']}:{svc['name']}")
    builder.button(text=BTN["back"], callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


# ── Misc ──────────────────────────────────────────────────────────────────────

def segments_kb() -> InlineKeyboardMarkup:
    """Inline keyboard for choosing a price segment."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Budget", callback_data="seg:budget"),
        InlineKeyboardButton(text="Standard", callback_data="seg:standard"),
        InlineKeyboardButton(text="Premium", callback_data="seg:premium"),
    ]])


def yes_no_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    """Generic yes/no inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN["yes"], callback_data=yes_cb),
        InlineKeyboardButton(text=BTN["no"], callback_data=no_cb),
    ]])
