from sqlite3 import Row

from config import SEGMENTS

STATUS_RU = {
    "pending": "ожидает",
    "confirmed": "подтверждена",
    "cancelled": "отменена",
    "completed": "завершена",
    "approved": "одобрен",
    "rejected": "отклонён",
    "blocked": "заблокирован",
}


def stars(rating: float) -> str:
    filled = round(float(rating))
    filled = max(0, min(5, filled))
    return "★" * filled + "☆" * (5 - filled)


def segment_title(code: str) -> str:
    return SEGMENTS.get(code, {}).get("title", code)


def barber_card(barber: Row) -> str:
    return (
        f"{barber['name']}\n"
        f"{stars(barber['rating'])}  {barber['rating']:.1f}\n"
        f"{segment_title(barber['segment'])}  ${barber['price_min']}–${barber['price_max']}\n"
        f"{barber['bio'] or 'Без описания'}"
    )


def booking_card(booking: Row) -> str:
    return (
        f"Заявка #{booking['id']}\n"
        f"Клиент: {booking['client_name']}\n"
        f"Телефон: {booking['phone']}\n"
        f"Услуга: {booking['service_title']} — ${booking['price_usd']}\n"
        f"Барбер: {booking['barber_name']}\n"
        f"Статус: {STATUS_RU.get(booking['status'], booking['status'])}"
    )


def draft_card(data: dict, service_title: str, barber: Row, price: int) -> str:
    return (
        "Проверьте запись перед отправкой:\n\n"
        f"Имя: {data.get('name')}\n"
        f"Телефон: {data.get('phone')}\n"
        f"Услуга: {service_title} — ${price}\n"
        f"Барбер: {barber['name']}  {stars(barber['rating'])} {barber['rating']:.1f}\n"
        f"Сегмент: {segment_title(barber['segment'])}  "
        f"${barber['price_min']}–${barber['price_max']}"
    )
