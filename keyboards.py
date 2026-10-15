from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from sqlite3 import Row

from config import SEGMENTS
from db import Database
from formatters import STATUS_RU, stars


def main_keyboard(user_id: int, admin_id: int, db: Database) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Записаться на услугу")],
        [KeyboardButton(text="Мои заявки")],
    ]
    barber = db.get_barber(user_id)
    if barber and barber["status"] == "approved":
        rows.append([KeyboardButton(text="Кабинет барбера")])
    elif barber and barber["status"] == "pending":
        rows.append([KeyboardButton(text="Статус заявки барбера")])
    else:
        rows.append([KeyboardButton(text="Стать барбером")])
    if user_id == admin_id:
        rows.append([KeyboardButton(text="Админ-панель")])
    rows.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить свой номер", request_contact=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )


def services_keyboard(services: list[Row], prefix: str = "svc") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item['title']} — ${item['price_usd']}",
                callback_data=f"{prefix}:{item['id']}",
            )
        ]
        for item in services
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def barbers_keyboard(barbers: list[Row]) -> InlineKeyboardMarkup:
    rows = []
    for barber in barbers:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{barber['name']}  {stars(barber['rating'])} "
                        f"${barber['price_min']}–${barber['price_max']}"
                    ),
                    callback_data=f"brb:{barber['user_id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить запись", callback_data="bk:ok")],
            [
                InlineKeyboardButton(text="Изменить имя", callback_data="bk:ed:name"),
                InlineKeyboardButton(text="Изменить телефон", callback_data="bk:ed:phone"),
            ],
            [
                InlineKeyboardButton(text="Изменить услугу", callback_data="bk:ed:svc"),
                InlineKeyboardButton(text="Изменить барбера", callback_data="bk:ed:brb"),
            ],
            [InlineKeyboardButton(text="Отменить", callback_data="bk:cancel")],
        ]
    )


def bookings_keyboard(bookings: list[Row], prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for item in bookings:
        title = item["service_title"]
        extra = item["barber_name"] if "barber_name" in item.keys() else item["client_name"]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{item['id']} · {title} · {STATUS_RU.get(item['status'], item['status'])} · {extra}",
                    callback_data=f"{prefix}:{item['id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def client_booking_actions(booking_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="Изменить имя", callback_data=f"ced:{booking_id}:name"),
                InlineKeyboardButton(text="Изменить телефон", callback_data=f"ced:{booking_id}:phone"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="Изменить услугу", callback_data=f"ced:{booking_id}:svc"),
                InlineKeyboardButton(text="Изменить барбера", callback_data=f"ced:{booking_id}:brb"),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"ccl:{booking_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def barber_booking_actions(booking_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"bacc:{booking_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"brej:{booking_id}"),
            ]
        )
    if status in {"pending", "confirmed"}:
        rows.append(
            [
                InlineKeyboardButton(text="Сменить услугу", callback_data=f"bed:{booking_id}:svc"),
                InlineKeyboardButton(text="Сменить цену", callback_data=f"bed:{booking_id}:price"),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="Завершить", callback_data=f"bdn:{booking_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def segments_keyboard(prefix: str = "seg") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item['title']}  ${item['price_min']}–${item['price_max']}",
                callback_data=f"{prefix}:{code}",
            )
        ]
        for code, item in SEGMENTS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def barber_cabinet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Входящие заявки", callback_data="cab:bookings")],
            [InlineKeyboardButton(text="Мой профиль", callback_data="cab:profile")],
            [
                InlineKeyboardButton(text="Имя", callback_data="cab:name"),
                InlineKeyboardButton(text="Описание", callback_data="cab:bio"),
            ],
            [
                InlineKeyboardButton(text="Рейтинг", callback_data="cab:rating"),
                InlineKeyboardButton(text="Сегмент", callback_data="cab:seg"),
            ],
            [InlineKeyboardButton(text="Цены на услуги", callback_data="cab:prices")],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Заявки барберов", callback_data="adm:pending")],
            [InlineKeyboardButton(text="Все барберы", callback_data="adm:barbers")],
            [InlineKeyboardButton(text="Все записи", callback_data="adm:bookings")],
            [InlineKeyboardButton(text="Цены услуг студии", callback_data="adm:services")],
        ]
    )


def admin_barber_actions(user_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"aap:{user_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"arj:{user_id}"),
            ]
        )
    if status == "approved":
        rows.append([InlineKeyboardButton(text="Заблокировать", callback_data=f"abl:{user_id}")])
    if status in {"rejected", "blocked"}:
        rows.append([InlineKeyboardButton(text="Одобрить снова", callback_data=f"aap:{user_id}")])
    rows.append(
        [
            InlineKeyboardButton(text="Имя", callback_data=f"aed:{user_id}:name"),
            InlineKeyboardButton(text="Рейтинг", callback_data=f"aed:{user_id}:rating"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="Ценовой сегмент", callback_data=f"aed:{user_id}:seg")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
