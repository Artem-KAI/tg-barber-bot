"""FSM state groups for all conversation flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup

__all__ = [
    "BookingFSM",
    "BarberApplyFSM",
    "BarberEditFSM",
    "BarberScheduleFSM",
    "BarberDaysOffFSM",
    "AdminFSM",
    "TEXT_INPUT_STATES",
]


class BookingFSM(StatesGroup):
    """States for the client booking flow."""

    name = State()
    phone = State()
    service = State()
    barber = State()
    date = State()
    time_slot = State()
    confirm = State()
    # Edit sub-states (while browsing own bookings)
    edit_name = State()
    edit_phone = State()


class BarberApplyFSM(StatesGroup):
    """States for the 'Become a Barber' application flow."""

    name = State()
    bio = State()
    segment = State()


class BarberEditFSM(StatesGroup):
    """States for barber profile editing inside the cabinet."""

    name = State()
    bio = State()
    segment = State()
    service_price = State()   # editing a specific service price
    change_price = State()    # barber changing booking price


class BarberScheduleFSM(StatesGroup):
    """States for setting the barber's weekly schedule."""

    days = State()   # step 1 — choosing weekdays
    slots = State()  # step 2 — choosing time slots


class BarberDaysOffFSM(StatesGroup):
    """States for toggling individual day-off dates."""

    picking = State()


class AdminFSM(StatesGroup):
    """States for admin-panel flows."""

    set_service_price = State()
    set_rating = State()


# States where the user types free text. Main-menu commands must not fire in
# them, otherwise a name like "Location" would be treated as a menu command.
TEXT_INPUT_STATES: tuple[State, ...] = (
    BookingFSM.name,
    BookingFSM.phone,
    BookingFSM.edit_name,
    BookingFSM.edit_phone,
    BarberApplyFSM.name,
    BarberApplyFSM.bio,
    BarberEditFSM.name,
    BarberEditFSM.bio,
    BarberEditFSM.service_price,
    BarberEditFSM.change_price,
    AdminFSM.set_service_price,
    AdminFSM.set_rating,
)
