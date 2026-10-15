import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
DB_PATH = os.getenv("DB_PATH", os.path.join("data", "bot.db"))

SEGMENTS = {
    "economy": {"title": "Economy", "price_min": 20, "price_max": 40},
    "standard": {"title": "Standard", "price_min": 40, "price_max": 70},
    "premium": {"title": "Premium", "price_min": 70, "price_max": 120},
}

DEFAULT_SERVICES = [
    ("consultation", "Консультация", 25),
    ("full_service", "Полный сервис", 55),
    ("express", "Экспресс-услуга", 35),
]


def load_settings() -> tuple[str, int]:
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        logging.error("Укажите настоящий BOT_TOKEN в файле .env")
        sys.exit(1)
    if not ADMIN_ID_RAW:
        logging.error("Укажите ADMIN_ID в файле .env")
        sys.exit(1)
    try:
        admin_id = int(ADMIN_ID_RAW)
    except ValueError:
        logging.error("ADMIN_ID должен быть числом")
        sys.exit(1)
    return BOT_TOKEN, admin_id
