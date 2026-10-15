from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from db import Database
from keyboards import main_keyboard
from utils import cancel_flow

router = Router()
fallback_router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    await message.answer(
        "Добро пожаловать в барбер-студию.\n\n"
        "Можно записаться к мастеру, выбрать услугу и ценовой сегмент в долларах, "
        "а также отредактировать заявку до подтверждения.\n\n"
        "Хотите принимать клиентов — оставьте заявку «Стать барбером».",
        reply_markup=main_keyboard(user_id, admin_id, db),
    )


@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
async def cmd_cancel(message: Message, state: FSMContext, db: Database, admin_id: int) -> None:
    await cancel_flow(message, state, db, admin_id)


@router.message(F.text == "Статус заявки барбера", StateFilter(None))
async def barber_status(message: Message, db: Database) -> None:
    if not message.from_user:
        return
    barber = db.get_barber(message.from_user.id)
    if not barber:
        await message.answer("Вы ещё не подавали заявку. Нажмите «Стать барбером».")
        return
    status = {
        "pending": "на рассмотрении у администратора",
        "approved": "одобрена — откройте «Кабинет барбера»",
        "rejected": "отклонена. Можно подать заявку снова",
        "blocked": "аккаунт барбера заблокирован",
    }.get(barber["status"], barber["status"])
    await message.answer(f"Статус заявки барбера: {status}.")


@fallback_router.message(StateFilter(None))
async def fallback(message: Message, db: Database, admin_id: int) -> None:
    user_id = message.from_user.id if message.from_user else 0
    await message.answer(
        "Выберите действие в меню. /start — главное меню, /cancel — отмена сценария.",
        reply_markup=main_keyboard(user_id, admin_id, db),
    )


@fallback_router.message()
async def fallback_busy(message: Message) -> None:
    await message.answer("Сейчас нужно ответить на текущий шаг или нажать «Отмена».")
