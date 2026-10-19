"""Booking card and profile card formatters (clean typography, no emojis)."""
from __future__ import annotations

import datetime
from html import escape

from app.texts import WEEKDAY_SHORT

__all__ = [
    "format_booking_card",
    "format_barber_profile",
    "format_service_list",
]


def _fmt_datetime(slot_datetime: str | None) -> str:
    """Convert 'YYYY-MM-DD HH:MM' to 'Mon, Oct 20 · 11:00 AM'."""
    if not slot_datetime:
        return "Not scheduled"
    try:
        dt = datetime.datetime.strptime(slot_datetime, "%Y-%m-%d %H:%M")
        weekday_abbr = WEEKDAY_SHORT[dt.weekday()]
        hour = dt.strftime("%I").lstrip("0") or "12"
        time_str = f"{hour}:{dt.strftime('%M %p')}"
        date_str = f"{dt.strftime('%b')} {dt.day}"
        return f"{weekday_abbr}, {date_str} · {time_str}"
    except Exception:
        return slot_datetime


def format_booking_card(booking: dict) -> str:
    """
    Format a booking row (dict-like) into a clean HTML card string.
    """
    if not isinstance(booking, dict) and hasattr(booking, "keys"):
        booking = dict(booking)

    barber_line = ""
    if booking.get("barber_name"):
        barber_line = f"Barber: <b>{escape(str(booking['barber_name']))}</b>\n"

    date_line = ""
    if booking.get("slot_datetime"):
        date_line = f"Date &amp; Time: <b>{_fmt_datetime(booking['slot_datetime'])}</b>\n"

    price = booking.get("price") or 0
    status = (booking.get("status") or "pending").capitalize()

    return (
        f"<b>Booking #{booking['id']}</b>\n"
        f"Client: <b>{escape(str(booking.get('client_name') or '—'))}</b>\n"
        f"Phone: <b>{escape(str(booking.get('client_phone') or '—'))}</b>\n"
        f"Service: <b>{escape(str(booking.get('service_name') or '—'))}</b>\n"
        f"{barber_line}"
        f"{date_line}"
        f"Price: <b>${price:.0f}</b>\n"
        f"Status: <b>{status}</b>"
    )


def format_barber_profile(barber: dict) -> str:
    """Format a barber profile row into a clean HTML card."""
    if not isinstance(barber, dict) and hasattr(barber, "keys"):
        barber = dict(barber)

    segment = (barber.get("segment") or "standard").capitalize()
    rating = barber.get("rating") or 5.0
    bio = escape(barber.get("bio") or "No bio provided.")
    return (
        f"<b>{escape(barber.get('name') or 'Barber')}</b>\n"
        f"Bio: {bio}\n"
        f"Rating: <b>{rating}</b>\n"
        f"Segment: <b>{segment}</b>\n"
        f"Status: <b>{(barber.get('status') or 'pending').capitalize()}</b>"
    )


def format_service_list(services: list) -> str:
    """Format a list of service rows into a readable HTML list."""
    if not services:
        return "No services configured."
    lines: list[str] = []
    for svc in services:
        lines.append(f"• <b>{escape(svc['name'])}</b> — ${svc['price']:.0f}")
    return "\n".join(lines)
