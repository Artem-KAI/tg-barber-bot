from aiogram.fsm.state import State, StatesGroup


class BookingFSM(StatesGroup):
    name = State()
    phone = State()
    service = State()
    barber = State()
    confirm = State()


class BarberApplyFSM(StatesGroup):
    name = State()
    bio = State()
    segment = State()


class BarberEditFSM(StatesGroup):
    name = State()
    bio = State()
    rating = State()
    price = State()


class AdminEditFSM(StatesGroup):
    service_price = State()
    barber_name = State()
    barber_rating = State()
    barber_segment = State()
