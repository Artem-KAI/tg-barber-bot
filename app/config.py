"""Configuration — loads settings from .env via python-dotenv."""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

__all__ = ["Settings", "settings", "local_now", "local_today"]

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    bot_token: str
    admin_id: int
    db_path: str = "data/bot.db"
    timezone: str = "America/New_York"


def _load() -> Settings:
    token = os.getenv("BOT_TOKEN")
    admin_raw = os.getenv("ADMIN_ID")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in .env")
    if not admin_raw:
        raise RuntimeError("ADMIN_ID is not set in .env")
    try:
        admin_id = int(admin_raw)
    except ValueError:
        raise RuntimeError("ADMIN_ID in .env must be a numeric Telegram user ID") from None
    timezone = os.getenv("TIMEZONE") or "America/New_York"
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise RuntimeError(
            f"TIMEZONE={timezone!r} is unknown (on Windows run: pip install tzdata)"
        ) from None
    return Settings(
        bot_token=token,
        admin_id=admin_id,
        db_path=os.getenv("DB_PATH") or "data/bot.db",
        timezone=timezone,
    )


settings: Settings = _load()
_TZ = ZoneInfo(settings.timezone)


def local_now() -> datetime.datetime:
    """Current wall-clock time at the barbershop (naive, in the shop's timezone)."""
    return datetime.datetime.now(_TZ).replace(tzinfo=None)


def local_today() -> datetime.date:
    """Current date at the barbershop."""
    return local_now().date()
