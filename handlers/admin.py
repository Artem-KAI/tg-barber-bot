from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import SEGMENTS
from db import Database
from formatters import STATUS_RU, barber_card, booking_card, segment_title
from keyboards import admin_barber_actions, admin_keyboard, bookings_keyboard, segments_keyboard, services_keyboard
from states import AdminEditFSM
from utils import menu_markup, parse_rating, parse_usd, safe_send

router = Router()


def require_admin(user_id: int | None, admin_id: int) -> bool:
    return user_id == admin_id


@router.message(F.text == "Админ-панель", StateFilter(None))
async def admin_home(message: Message, admin_id: int) -> None:
    if not require_admin(message.from_user.id if message.from_user else None, admin_id):
        await message.answer("Эта панель только для администратора.")
        return
    await message.answer(
        "Админ-панель: одобрение барберов, записи, рейтинги и цены студии.",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "adm:pending")
async def admin_pending(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pending = db.list_barbers("pending")
    if not callback.message:
        await callback.answer()
        return
    if not pending:
        await callback.message.answer("Нет заявок барберов.")
        await callback.answer()
        return
    rows = [
        [InlineKeyboardButton(text=item["name"], callback_data=f"ashow:{item['user_id']}")]
        for item in pending
    ]
    await callback.message.answer(
        "Заявки на регистрацию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:barbers")
async def admin_barbers(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    barbers = db.list_barbers()
    if not callback.message:
        await callback.answer()
        return
    if not barbers:
        await callback.message.answer("Барберов пока нет.")
        await callback.answer()
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item['name']} · {STATUS_RU.get(item['status'], item['status'])}",
                callback_data=f"ashow:{item['user_id']}",
            )
        ]
        for item in barbers
    ]
    await callback.message.answer("Все барберы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ashow:"))
async def admin_show_barber(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])
    barber = db.get_barber(user_id)
    if not barber:
        await callback.answer("Не найден", show_alert=True)
        return
    await callback.message.answer(
        barber_card(barber) + f"\nСтатус: {STATUS_RU.get(barber['status'], barber['status'])}\nID: {user_id}",
        reply_markup=admin_barber_actions(user_id, barber["status"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("aap:"))
async def admin_approve(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    await set_status(callback, db, admin_id, "approved", "Вас одобрили как барбера. Откройте «Кабинет барбера».")


@router.callback_query(F.data.startswith("arj:"))
async def admin_reject(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    await set_status(callback, db, admin_id, "rejected", "Заявка барбера отклонена.")


@router.callback_query(F.data.startswith("abl:"))
async def admin_block(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    await set_status(callback, db, admin_id, "blocked", "Ваш аккаунт барбера заблокирован.")


async def set_status(
    callback: CallbackQuery,
    db: Database,
    admin_id: int,
    status: str,
    user_text: str,
) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])
    db.set_barber_status(user_id, status)
    await safe_send(callback.bot, user_id, user_text)
    if callback.message:
        await callback.message.answer(f"Статус барбера {user_id}: {STATUS_RU.get(status, status)}")
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("aed:"))
async def admin_edit_barber(callback: CallbackQuery, state: FSMContext, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    _, user_id_raw, field = callback.data.split(":")
    user_id = int(user_id_raw)
    await state.update_data(target_barber_id=user_id)
    if field == "name":
        await state.set_state(AdminEditFSM.barber_name)
        await callback.message.answer("Новое имя барбера:")
    elif field == "rating":
        await state.set_state(AdminEditFSM.barber_rating)
        await callback.message.answer("Новый рейтинг от 1.0 до 5.0:")
    elif field == "seg":
        await state.set_state(AdminEditFSM.barber_segment)
        await callback.message.answer(
            "Выберите сегмент:",
            reply_markup=segments_keyboard("adseg"),
        )
    await callback.answer()


@router.message(AdminEditFSM.barber_name)
async def admin_save_name(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not require_admin(message.from_user.id if message.from_user else None, admin_id):
        return
    name = (message.text or "").strip()
    data = await state.get_data()
    db.update_barber(int(data["target_barber_id"]), name=name)
    await state.clear()
    await message.answer("Имя барбера обновлено.", reply_markup=await menu_markup(message, db, admin_id))


@router.message(AdminEditFSM.barber_rating)
async def admin_save_rating(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not require_admin(message.from_user.id if message.from_user else None, admin_id):
        return
    rating = parse_rating(message.text or "")
    if rating is None:
        await message.answer("Введите число от 1 до 5.")
        return
    data = await state.get_data()
    db.update_barber(int(data["target_barber_id"]), rating=rating)
    await state.clear()
    await message.answer(f"Рейтинг обновлён: {rating:.1f}", reply_markup=await menu_markup(message, db, admin_id))


@router.callback_query(AdminEditFSM.barber_segment, F.data.startswith("adseg:"))
async def admin_save_segment(callback: CallbackQuery, state: FSMContext, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data:
        await callback.answer()
        return
    segment = callback.data.split(":")[1]
    if segment not in SEGMENTS:
        await callback.answer("Неизвестный сегмент", show_alert=True)
        return
    data = await state.get_data()
    db.update_barber(int(data["target_barber_id"]), segment=segment)
    await state.clear()
    spec = SEGMENTS[segment]
    if callback.message:
        await callback.message.answer(
            f"Сегмент: {segment_title(segment)} ${spec['price_min']}–${spec['price_max']}",
            reply_markup=await menu_markup(callback, db, admin_id),
        )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "adm:bookings")
async def admin_bookings(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    items = db.all_bookings()
    if not callback.message:
        await callback.answer()
        return
    if not items:
        await callback.message.answer("Заявок пока нет.")
        await callback.answer()
        return
    await callback.message.answer("Все заявки:", reply_markup=bookings_keyboard(items, "abk"))
    await callback.answer()


@router.callback_query(F.data.startswith("abk:"))
async def admin_open_booking(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    booking = db.get_booking(int(callback.data.split(":")[1]))
    if not booking:
        await callback.answer("Не найдена", show_alert=True)
        return
    await callback.message.answer(booking_card(booking))
    await callback.answer()


@router.callback_query(F.data == "adm:services")
async def admin_services(callback: CallbackQuery, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.message:
        await callback.answer()
        return
    await callback.message.answer(
        "Базовые цены студии. Нажмите услугу, чтобы изменить цену в долларах:",
        reply_markup=services_keyboard(db.get_services(), prefix="apr"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("apr:"))
async def admin_ask_service_price(callback: CallbackQuery, state: FSMContext, db: Database, admin_id: int) -> None:
    if not require_admin(callback.from_user.id if callback.from_user else None, admin_id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    service_id = int(callback.data.split(":")[1])
    service = db.get_service(service_id)
    if not service:
        await callback.answer("Не найдена", show_alert=True)
        return
    await state.set_state(AdminEditFSM.service_price)
    await state.update_data(service_id=service_id)
    await callback.message.answer(f"Новая базовая цена для «{service['title']}» в $:")
    await callback.answer()


@router.message(AdminEditFSM.service_price)
async def admin_save_service_price(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    if not require_admin(message.from_user.id if message.from_user else None, admin_id):
        return
    price = parse_usd(message.text or "")
    if price is None:
        await message.answer("Введите сумму в долларах.")
        return
    data = await state.get_data()
    db.update_service_price(int(data["service_id"]), price)
    await state.clear()
    await message.answer(
        f"Базовая цена обновлена: ${price}. Новые барберы будут получать её по умолчанию.",
        reply_markup=await menu_markup(message, db, admin_id),
    )
