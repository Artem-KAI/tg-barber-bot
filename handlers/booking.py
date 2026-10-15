from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from db import Database
from formatters import booking_card, draft_card
from keyboards import (
    barbers_keyboard,
    bookings_keyboard,
    cancel_keyboard,
    client_booking_actions,
    confirm_keyboard,
    main_keyboard,
    phone_keyboard,
    services_keyboard,
)
from states import BookingFSM
from utils import menu_markup, safe_send

router = Router()


async def ask_name(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingFSM.name)
    await message.answer("Как к вам обращаться?", reply_markup=cancel_keyboard())


async def ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingFSM.phone)
    await message.answer(
        "Укажите номер телефона или нажмите «Отправить свой номер».",
        reply_markup=phone_keyboard(),
    )


async def ask_service(target: Message, state: FSMContext, db: Database) -> None:
    await state.set_state(BookingFSM.service)
    await target.answer("Выберите услугу. Цены указаны в долларах.", reply_markup=ReplyKeyboardRemove())
    await target.answer("Услуги студии:", reply_markup=services_keyboard(db.get_services()))


async def ask_barber(target: Message, state: FSMContext, db: Database) -> None:
    barbers = db.approved_barbers()
    if not barbers:
        await target.answer("Пока нет доступных барберов. Попробуйте позже.")
        return
    await state.set_state(BookingFSM.barber)
    lines = ["Выберите барбера. У каждого мастера свой рейтинг и ценовой сегмент:\n"]
    for barber in barbers:
        lines.append(
            f"• {barber['name']} — {barber['rating']:.1f}/5, "
            f"{barber['segment'].title()} ${barber['price_min']}–${barber['price_max']}"
        )
    await target.answer("\n".join(lines), reply_markup=barbers_keyboard(barbers))


async def show_confirm(target: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    service = db.get_service(int(data["service_id"]))
    barber = db.get_barber(int(data["barber_id"]))
    if not service or not barber:
        await target.answer("Не удалось собрать заявку. Начните запись заново.")
        await state.clear()
        return
    price = db.service_price_for_barber(barber["user_id"], service["id"])
    await state.update_data(price_usd=price)
    await state.set_state(BookingFSM.confirm)
    await target.answer(
        draft_card(data, service["title"], barber, price),
        reply_markup=confirm_keyboard(),
    )


def after_edit_returns_to_confirm(data: dict) -> bool:
    return bool(data.get("return_confirm")) and not data.get("booking_id")


@router.message(F.text == "Записаться на услугу", StateFilter(None))
async def start_booking(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(return_confirm=False)
    await ask_name(message, state)


@router.message(BookingFSM.name)
async def process_name(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not message.text:
        await message.answer("Отправьте имя текстом.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое.")
        return

    data = await state.get_data()
    booking_id = data.get("booking_id")
    if booking_id:
        db.update_booking(int(booking_id), client_name=name)
        await finish_existing_edit(message, state, db, admin_id, int(booking_id), "имя")
        return

    await state.update_data(name=name)
    if after_edit_returns_to_confirm(data):
        await show_confirm(message, state, db)
        return
    await ask_phone(message, state)


@router.message(BookingFSM.phone, F.contact)
async def process_phone_contact(
    message: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    contact = message.contact
    if not contact or not contact.phone_number:
        await message.answer("Не удалось получить номер.")
        return
    if contact.user_id and message.from_user and contact.user_id != message.from_user.id:
        await message.answer("Отправьте именно свой номер.", reply_markup=phone_keyboard())
        return
    await save_phone(message, state, db, admin_id, contact.phone_number)


@router.message(BookingFSM.phone, F.text)
async def process_phone_text(
    message: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    phone = (message.text or "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        await message.answer("Это не похоже на телефон.", reply_markup=phone_keyboard())
        return
    await save_phone(message, state, db, admin_id, phone)


async def save_phone(
    message: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
    phone: str,
) -> None:
    data = await state.get_data()
    booking_id = data.get("booking_id")
    if booking_id:
        db.update_booking(int(booking_id), phone=phone)
        await finish_existing_edit(message, state, db, admin_id, int(booking_id), "телефон")
        return

    await state.update_data(phone=phone)
    if after_edit_returns_to_confirm(data):
        await message.answer("Телефон обновлён.", reply_markup=ReplyKeyboardRemove())
        await show_confirm(message, state, db)
        return
    await ask_service(message, state, db)


@router.callback_query(BookingFSM.service, F.data.startswith("svc:"))
async def process_service(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    if not callback.message or not callback.data:
        await callback.answer()
        return
    service_id = int(callback.data.split(":")[1])
    service = db.get_service(service_id)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    data = await state.get_data()
    booking_id = data.get("booking_id")
    if booking_id:
        booking = db.get_booking(int(booking_id))
        if not booking:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        price = db.service_price_for_barber(booking["barber_id"], service_id)
        db.update_booking(int(booking_id), service_id=service_id, price_usd=price)
        await notify_booking_changed(callback.bot, db, int(booking_id), "услугу")
        await state.clear()
        await callback.message.answer(
            "Услуга в заявке обновлена.",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
        await callback.answer("Сохранено")
        return

    await state.update_data(service_id=service_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    if after_edit_returns_to_confirm(data) and data.get("barber_id"):
        await show_confirm(callback.message, state, db)
        await callback.answer()
        return
    await ask_barber(callback.message, state, db)
    await callback.answer()


@router.callback_query(BookingFSM.barber, F.data.startswith("brb:"))
async def process_barber(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    if not callback.message or not callback.data:
        await callback.answer()
        return
    barber_id = int(callback.data.split(":")[1])
    barber = db.get_barber(barber_id)
    if not barber or barber["status"] != "approved":
        await callback.answer("Этот барбер недоступен", show_alert=True)
        return

    data = await state.get_data()
    booking_id = data.get("booking_id")
    if booking_id:
        booking = db.get_booking(int(booking_id))
        if not booking:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        old_barber_id = booking["barber_id"]
        price = db.service_price_for_barber(barber_id, booking["service_id"])
        db.update_booking(int(booking_id), barber_id=barber_id, price_usd=price)
        updated = db.get_booking(int(booking_id))
        if updated and old_barber_id != barber_id:
            await safe_send(
                callback.bot,
                old_barber_id,
                f"Клиент перенёс заявку #{booking_id} к другому мастеру.",
            )
            await safe_send(
                callback.bot,
                barber_id,
                "Вам передали заявку:\n\n" + booking_card(updated),
            )
        await callback.message.answer(
            "Барбер в заявке обновлён.",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
        await state.clear()
        await callback.answer("Сохранено")
        return

    await state.update_data(barber_id=barber_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await show_confirm(callback.message, state, db)
    await callback.answer()


@router.message(BookingFSM.service)
async def service_text(message: Message, db: Database) -> None:
    await message.answer(
        "Выберите услугу кнопкой ниже.",
        reply_markup=services_keyboard(db.get_services()),
    )


@router.message(BookingFSM.barber)
async def barber_text(message: Message, db: Database) -> None:
    await message.answer(
        "Выберите барбера кнопкой ниже.",
        reply_markup=barbers_keyboard(db.approved_barbers()),
    )


@router.callback_query(BookingFSM.confirm, F.data == "bk:ok")
async def confirm_booking(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_id: int,
    bot: Bot,
) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    data = await state.get_data()
    required = ("name", "phone", "service_id", "barber_id")
    if any(key not in data for key in required):
        await callback.answer("Данные неполные, начните запись заново", show_alert=True)
        await state.clear()
        return

    barber_id = int(data["barber_id"])
    service_id = int(data["service_id"])
    price = db.service_price_for_barber(barber_id, service_id)
    booking_id = db.create_booking(
        client_id=callback.from_user.id,
        barber_id=barber_id,
        service_id=service_id,
        client_name=data["name"],
        phone=data["phone"],
        price_usd=price,
    )
    booking = db.get_booking(booking_id)
    await state.clear()

    if booking:
        sent = await safe_send(
            bot,
            barber_id,
            "Новая заявка от клиента:\n\n" + booking_card(booking),
        )
        if not sent and barber_id != admin_id:
            await safe_send(bot, admin_id, "Барбер не получил заявку:\n\n" + booking_card(booking))

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Заявка отправлена выбранному барберу.\n\n" + booking_card(booking)
            + "\n\nПока мастер не подтвердил запись, её можно изменить в разделе «Мои заявки».",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
    await callback.answer("Отправлено")


@router.callback_query(BookingFSM.confirm, F.data == "bk:ed:name")
async def edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(return_confirm=True)
    if callback.message:
        await ask_name(callback.message, state)
    await callback.answer()


@router.callback_query(BookingFSM.confirm, F.data == "bk:ed:phone")
async def edit_phone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(return_confirm=True)
    if callback.message:
        await ask_phone(callback.message, state)
    await callback.answer()


@router.callback_query(BookingFSM.confirm, F.data == "bk:ed:svc")
async def edit_service(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.update_data(return_confirm=True)
    if callback.message:
        await ask_service(callback.message, state, db)
    await callback.answer()


@router.callback_query(BookingFSM.confirm, F.data == "bk:ed:brb")
async def edit_barber(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.update_data(return_confirm=True)
    if callback.message:
        await ask_barber(callback.message, state, db)
    await callback.answer()


@router.callback_query(F.data == "bk:cancel")
async def cancel_draft(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_id: int,
) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer(
            "Черновик записи отменён.",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
    await callback.answer()


@router.message(F.text == "Мои заявки", StateFilter(None))
async def my_bookings(message: Message, db: Database) -> None:
    if not message.from_user:
        return
    items = db.client_bookings(message.from_user.id)
    if not items:
        await message.answer("У вас пока нет заявок.")
        return
    await message.answer("Ваши заявки. Нажмите, чтобы открыть и отредактировать:")
    await message.answer("Список:", reply_markup=bookings_keyboard(items, "cbk"))


@router.callback_query(F.data.startswith("cbk:"))
async def open_client_booking(callback: CallbackQuery, db: Database) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    booking = db.get_booking(booking_id)
    if not booking or booking["client_id"] != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if callback.message:
        await callback.message.answer(
            booking_card(booking),
            reply_markup=client_booking_actions(booking_id, booking["status"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("ced:"))
async def edit_existing(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    _, booking_id_raw, field = callback.data.split(":")
    booking_id = int(booking_id_raw)
    booking = db.get_booking(booking_id)
    if not booking or booking["client_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if booking["status"] != "pending":
        await callback.answer("Эту заявку уже нельзя менять", show_alert=True)
        return

    await state.clear()
    await state.update_data(booking_id=booking_id, return_confirm=False)
    if field == "name":
        await ask_name(callback.message, state)
    elif field == "phone":
        await ask_phone(callback.message, state)
    elif field == "svc":
        await ask_service(callback.message, state, db)
    elif field == "brb":
        await ask_barber(callback.message, state, db)
    await callback.answer()


@router.callback_query(F.data.startswith("ccl:"))
async def cancel_existing(
    callback: CallbackQuery,
    db: Database,
    admin_id: int,
) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    booking = db.get_booking(booking_id)
    if not booking or booking["client_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if booking["status"] != "pending":
        await callback.answer("Заявку уже нельзя отменить", show_alert=True)
        return
    db.update_booking(booking_id, status="cancelled")
    await safe_send(callback.bot, booking["barber_id"], f"Клиент отменил заявку #{booking_id}.")
    if callback.message:
        await callback.message.answer(
            "Заявка отменена.",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
    await callback.answer("Отменено")


async def finish_existing_edit(
    message: Message,
    state: FSMContext,
    db: Database,
    admin_id: int,
    booking_id: int,
    field_name: str,
) -> None:
    await notify_booking_changed(message.bot, db, booking_id, field_name)
    await state.clear()
    await message.answer(
        f"Поле «{field_name}» обновлено.",
        reply_markup=main_keyboard(message.from_user.id if message.from_user else 0, admin_id, db),
    )


async def notify_booking_changed(bot: Bot, db: Database, booking_id: int, field_name: str) -> None:
    booking = db.get_booking(booking_id)
    if not booking:
        return
    await safe_send(
        bot,
        booking["barber_id"],
        f"Клиент изменил {field_name} в заявке:\n\n" + booking_card(booking),
    )
