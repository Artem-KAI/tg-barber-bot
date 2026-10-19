"""Handlers package — exports setup_routers."""
from __future__ import annotations

from aiogram import Dispatcher

from handlers.common import router as common_router, fallback_router
from handlers.booking import router as booking_router
from handlers.barber import router as barber_router
from handlers.admin import router as admin_router

__all__ = ["setup_routers"]


def setup_routers(dp: Dispatcher) -> None:
    """Register all handler routers with the dispatcher."""
    dp.include_router(common_router)
    dp.include_router(booking_router)
    dp.include_router(barber_router)
    dp.include_router(admin_router)
    # The fallback catch-all MUST be included last
    dp.include_router(fallback_router)
