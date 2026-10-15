import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import DB_PATH, load_settings
from db import Database
from handlers import setup_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    token, admin_id = load_settings()
    db = Database(DB_PATH)
    db.ensure_admin_barber(admin_id)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp["db"] = db
    dp["admin_id"] = admin_id
    dp.include_router(setup_routers())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен. ADMIN_ID=%s", admin_id)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
