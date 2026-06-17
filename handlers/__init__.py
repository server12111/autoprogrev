from aiogram import Router

from . import accounts, admin, history, profile, start


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(accounts.router)
    root.include_router(profile.router)
    root.include_router(history.router)
    root.include_router(admin.router)
    return root
