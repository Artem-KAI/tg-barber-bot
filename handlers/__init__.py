from aiogram import Router

from handlers.admin import router as admin_router
from handlers.barber import router as barber_router
from handlers.booking import router as booking_router
from handlers.common import fallback_router, router as common_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(common_router)
    root.include_router(booking_router)
    root.include_router(barber_router)
    root.include_router(admin_router)
    root.include_router(fallback_router)
    return root
