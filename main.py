"""Entry point — starts the aiogram bot."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.db import db
from app.storage import SQLiteStorage
from app.texts import MSG
from handlers import setup_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

EXPIRE_INTERVAL_SECONDS = 300


async def expire_bookings_once(bot: Bot) -> None:
    """Expire pending bookings whose time has passed and tell the clients."""
    for bk in await db.expire_past_bookings():
        try:
            await bot.send_message(bk["client_id"], MSG["notify_client_expired"].format(id=bk["id"]))
        except Exception as e:
            logger.warning("Could not notify client %s: %s", bk["client_id"], e)


async def expire_bookings_loop(bot: Bot) -> None:
    """Run expire_bookings_once periodically until cancelled."""
    while True:
        try:
            await expire_bookings_once(bot)
        except Exception:
            logger.exception("Booking expiry failed")
        await asyncio.sleep(EXPIRE_INTERVAL_SECONDS)


async def main() -> None:
    """Initialise and run the bot until interrupted."""
    # Connect to the database
    await db.connect()
    logger.info("Database connected: %s", settings.db_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=SQLiteStorage(db))

    setup_routers(dp)

    expiry_task = asyncio.create_task(expire_bookings_loop(bot))
    logger.info("Starting The Iron Throne Barbershop bot…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        expiry_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await expiry_task
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
