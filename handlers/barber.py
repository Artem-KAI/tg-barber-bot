from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import SEGMENTS
from db import Database
from formatters import barber_card, booking_card, segment_title
from keyboards import (
    barber_booking_actions,
    barber_cabinet_keyboard,
    bookings_keyboard,
    cancel_keyboard,
    segments_keyboard,
    services_keyboard,
)
from states import BarberApplyFSM, BarberEditFSM
from utils import menu_markup, parse_rating, parse_usd, safe_send

router = Router()


def is_approved_barber(user_id: int, db: Database) -> bool:
    barber = db.get_barber(user_id)
    return bool(barber and barber["status"] == "approved")


@router.message(F.text == "Стать барбером", StateFilter(None))
async def start_apply(message: Message, state: FSMContext, db: Database) -> None:
    if not message.from_user:
        return
    existing = db.get_barber(message.from_user.id)
    if existing and existing["status"] == "approved":
        await message.answer("Вы уже зарегистрированы как барбер. Откройте «Кабинет барбера».")
        return
    if existing and existing["status"] == "pending":
        await message.answer("Ваша заявка уже на рассмотрении у администратора.")
        return
    if existing and existing["status"] == "blocked":
        await message.answer("Аккаунт барбера заблокирован. Напишите администратору.")
        return
    await state.set_state(BarberApplyFSM.name)
    await message.answer(
        "Регистрация барбера.\n\nКак будут видеть ваше имя клиенты?",
        reply_markup=cancel_keyboard(),
    )


@router.message(BarberApplyFSM.name)
async def apply_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введите имя подлиннее.")
        return
    await state.update_data(name=name)
    await state.set_state(BarberApplyFSM.bio)
    await message.answer("Коротко опишите себя и стиль работы.")


@router.message(BarberApplyFSM.bio)
async def apply_bio(message: Message, state: FSMContext) -> None:
    bio = (message.text or "").strip()
    if len(bio) < 5:
        await message.answer("Описание слишком короткое.")
        return
    await state.update_data(bio=bio)
    await state.set_state(BarberApplyFSM.segment)
    await message.answer(
        "Выберите ценовой сегмент в долларах. Клиенты увидят его рядом с рейтингом.",
        reply_markup=segments_keyboard("aseg"),
    )


@router.callback_query(BarberApplyFSM.segment, F.data.startswith("aseg:"))
async def apply_segment(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    segment = callback.data.split(":")[1]
    if segment not in SEGMENTS:
        await callback.answer("Неизвестный сегмент", show_alert=True)
        return
    data = await state.get_data()
    db.upsert_barber(
        user_id=callback.from_user.id,
        name=data["name"],
        bio=data["bio"],
        segment=segment,
        status="pending",
        rating=4.7,
    )
    await state.clear()
    spec = SEGMENTS[segment]
    await safe_send(
        callback.bot,
        admin_id,
        "Новая заявка барбера:\n"
        f"Имя: {data['name']}\n"
        f"ID: {callback.from_user.id}\n"
        f"Username: @{callback.from_user.username or 'нет'}\n"
        f"Сегмент: {spec['title']} ${spec['price_min']}–${spec['price_max']}\n"
        f"О себе: {data['bio']}\n\n"
        "Откройте «Админ-панель», чтобы одобрить или отклонить.",
    )
    await callback.message.answer(
        "Заявка отправлена администратору. После одобрения вы начнёте получать записи клиентов.",
        reply_markup=await menu_markup(callback, db, admin_id),
    )
    await callback.answer("Отправлено")


@router.message(F.text == "Кабинет барбера", StateFilter(None))
async def cabinet(message: Message, db: Database) -> None:
    if not message.from_user or not is_approved_barber(message.from_user.id, db):
        await message.answer("Кабинет доступен только одобренным барберам.")
        return
    barber = db.get_barber(message.from_user.id)
    if not barber:
        return
    await message.answer(
        "Кабинет барбера. Здесь можно менять профиль, рейтинг, цены и заявки.\n\n"
        + barber_card(barber),
        reply_markup=barber_cabinet_keyboard(),
    )


@router.callback_query(F.data == "cab:profile")
async def cab_profile(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    barber = db.get_barber(callback.from_user.id)
    if not barber or barber["status"] != "approved":
        await callback.answer("Нет доступа", show_alert=True)
        return
    services = db.barber_services(barber["user_id"])
    prices = "\n".join(f"• {item['title']}: ${item['price_usd']}" for item in services)
    if callback.message:
        await callback.message.answer(barber_card(barber) + "\n\nЦены:\n" + prices)
    await callback.answer()


@router.callback_query(F.data == "cab:bookings")
async def cab_bookings(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    if not is_approved_barber(callback.from_user.id, db):
        await callback.answer("Нет доступа", show_alert=True)
        return
    items = db.barber_bookings(callback.from_user.id)
    if not items:
        await callback.message.answer("Входящих заявок пока нет.")
        await callback.answer()
        return
    await callback.message.answer(
        "Ваши заявки:",
        reply_markup=bookings_keyboard(items, "bbk"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bbk:"))
async def open_barber_booking(callback: CallbackQuery, db: Database) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    booking = db.get_booking(booking_id)
    if not booking or booking["barber_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer(
        booking_card(booking),
        reply_markup=barber_booking_actions(booking_id, booking["status"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bacc:"))
async def accept_booking(callback: CallbackQuery, db: Database) -> None:
    await set_booking_status(callback, db, "confirmed", "Барбер подтвердил вашу запись.")


@router.callback_query(F.data.startswith("brej:"))
async def reject_booking(callback: CallbackQuery, db: Database) -> None:
    await set_booking_status(callback, db, "cancelled", "Барбер отклонил вашу запись.")


@router.callback_query(F.data.startswith("bdn:"))
async def complete_booking(callback: CallbackQuery, db: Database) -> None:
    await set_booking_status(callback, db, "completed", "Визит отмечен как завершённый.")


async def set_booking_status(callback: CallbackQuery, db: Database, status: str, client_text: str) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    booking = db.get_booking(booking_id)
    if not booking or booking["barber_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    db.update_booking(booking_id, status=status)
    updated = db.get_booking(booking_id)
    await safe_send(callback.bot, booking["client_id"], client_text + "\n\n" + booking_card(updated or booking))
    if callback.message and updated:
        await callback.message.answer("Статус обновлён.\n\n" + booking_card(updated))
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("bed:"))
async def barber_edit_booking(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    _, booking_id_raw, field = callback.data.split(":")
    booking_id = int(booking_id_raw)
    booking = db.get_booking(booking_id)
    if not booking or booking["barber_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if field == "svc":
        await state.set_state(BarberEditFSM.price)
        await state.update_data(edit_booking_id=booking_id, edit_mode="booking_service")
        await callback.message.answer(
            "Выберите новую услугу для заявки:",
            reply_markup=services_keyboard(db.get_services(), prefix="bsvc"),
        )
    elif field == "price":
        await state.set_state(BarberEditFSM.price)
        await state.update_data(edit_booking_id=booking_id, edit_mode="booking_price")
        await callback.message.answer("Введите новую цену заявки в долларах, например 45.")
    await callback.answer()


@router.callback_query(BarberEditFSM.price, F.data.startswith("bsvc:"))
async def barber_change_booking_service(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return
    data = await state.get_data()
    booking_id = int(data["edit_booking_id"])
    service_id = int(callback.data.split(":")[1])
    booking = db.get_booking(booking_id)
    if not booking or booking["barber_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    price = db.service_price_for_barber(callback.from_user.id, service_id)
    db.update_booking(booking_id, service_id=service_id, price_usd=price)
    updated = db.get_booking(booking_id)
    await state.clear()
    if updated:
        await safe_send(
            callback.bot,
            booking["client_id"],
            "Барбер изменил услугу в вашей заявке:\n\n" + booking_card(updated),
        )
        if callback.message:
            await callback.message.answer("Услуга обновлена.\n\n" + booking_card(updated))
    await callback.answer("Сохранено")


@router.message(BarberEditFSM.price)
async def barber_save_price_or_field(
    message: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    mode = data.get("edit_mode")
    if mode == "booking_price":
        price = parse_usd(message.text or "")
        if price is None:
            await message.answer("Введите сумму в долларах, например 40.")
            return
        booking_id = int(data["edit_booking_id"])
        booking = db.get_booking(booking_id)
        if not booking or booking["barber_id"] != message.from_user.id:
            await state.clear()
            return
        db.update_booking(booking_id, price_usd=price)
        updated = db.get_booking(booking_id)
        await state.clear()
        if updated:
            await safe_send(
                message.bot,
                booking["client_id"],
                "Барбер изменил цену заявки:\n\n" + booking_card(updated),
            )
            await message.answer(
                "Цена обновлена.\n\n" + booking_card(updated),
                reply_markup=await menu_markup(message, db, admin_id),
            )
        return

    if mode == "service_price":
        price = parse_usd(message.text or "")
        if price is None:
            await message.answer("Введите сумму в долларах.")
            return
        db.set_barber_service_price(message.from_user.id, int(data["service_id"]), price)
        await state.clear()
        await message.answer(
            f"Цена услуги обновлена: ${price}",
            reply_markup=await menu_markup(message, db, admin_id),
        )


@router.callback_query(F.data == "cab:name")
async def cab_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.set_state(BarberEditFSM.name)
    await callback.message.answer("Новое имя для профиля барбера:")
    await callback.answer()


@router.message(BarberEditFSM.name)
async def save_barber_name(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not message.from_user or not is_approved_barber(message.from_user.id, db):
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое.")
        return
    db.update_barber(message.from_user.id, name=name)
    await state.clear()
    await message.answer("Имя обновлено.", reply_markup=await menu_markup(message, db, admin_id))


@router.callback_query(F.data == "cab:bio")
async def cab_bio(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(BarberEditFSM.bio)
    await callback.message.answer("Новое описание профиля:")
    await callback.answer()


@router.message(BarberEditFSM.bio)
async def save_barber_bio(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not message.from_user or not is_approved_barber(message.from_user.id, db):
        return
    bio = (message.text or "").strip()
    if len(bio) < 5:
        await message.answer("Описание слишком короткое.")
        return
    db.update_barber(message.from_user.id, bio=bio)
    await state.clear()
    await message.answer("Описание обновлено.", reply_markup=await menu_markup(message, db, admin_id))


@router.callback_query(F.data == "cab:rating")
async def cab_rating(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(BarberEditFSM.rating)
    await callback.message.answer("Укажите рейтинг от 1.0 до 5.0, например 4.8")
    await callback.answer()


@router.message(BarberEditFSM.rating)
async def save_barber_rating(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not message.from_user or not is_approved_barber(message.from_user.id, db):
        return
    rating = parse_rating(message.text or "")
    if rating is None:
        await message.answer("Введите число от 1 до 5.")
        return
    db.update_barber(message.from_user.id, rating=rating)
    await state.clear()
    await message.answer(f"Рейтинг обновлён: {rating:.1f}", reply_markup=await menu_markup(message, db, admin_id))


@router.callback_query(F.data == "cab:seg")
async def cab_segment(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.message.answer(
        "Выберите ценовой сегмент:",
        reply_markup=segments_keyboard("bseg"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bseg:"))
async def save_segment(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return
    if not is_approved_barber(callback.from_user.id, db):
        await callback.answer("Нет доступа", show_alert=True)
        return
    segment = callback.data.split(":")[1]
    if segment not in SEGMENTS:
        await callback.answer("Неизвестный сегмент", show_alert=True)
        return
    db.update_barber(callback.from_user.id, segment=segment)
    spec = SEGMENTS[segment]
    if callback.message:
        await callback.message.answer(
            f"Сегмент: {segment_title(segment)} ${spec['price_min']}–${spec['price_max']}",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "cab:prices")
async def cab_prices(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    if not is_approved_barber(callback.from_user.id, db):
        await callback.answer("Нет доступа", show_alert=True)
        return
    services = db.barber_services(callback.from_user.id)
    await callback.message.answer(
        "Выберите услугу, цену которой хотите изменить:",
        reply_markup=services_keyboard(services, prefix="bpr"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bpr:"))
async def ask_service_price(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    service_id = int(callback.data.split(":")[1])
    service = db.get_service(service_id)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    await state.set_state(BarberEditFSM.price)
    await state.update_data(edit_mode="service_price", service_id=service_id)
    await callback.message.answer(f"Новая цена для «{service['title']}» в долларах:")
    await callback.answer()
