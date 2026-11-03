"""
MediODL Bot - Entrypoint
Run: python -m bot  (or python bot/main.py)
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN, LOG_LEVEL, TMP_DIR, COOKIES_DIR, DATABASE_PATH
from bot.db import init_db
from bot.handlers import user as user_handler
from bot.handlers import admin as admin_handler
from bot.middlewares.throttle import ThrottleMiddleware
from bot.utils.downloader import periodic_cleanup

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("main")
# Quieter noisy libs
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)

async def on_startup(bot: Bot):
    me = await bot.get_me()
    log.info("Bot @%s (%s) started. DB=%s TMP=%s", me.username, me.id, DATABASE_PATH, TMP_DIR)
    # Ensure dirs
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

async def main():
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        print("❌ BOT_TOKEN تنظیم نشده! فایل .env را چک کن. (BOT_TOKEN=1234:AAH...)")
        print("   راهنما: /opt/mediodl-bot/.env را ویرایش کن و سپس: mediodl restart")
        sys.exit(1)

    await init_db()

    # Bot instance - with optional Local Bot API server for >50MB uploads
    from bot.config import USE_LOCAL_API, BOT_API_SERVER, BOT_API_PORT
    bot_kwargs = {
        "token": BOT_TOKEN,
        "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
    }
    if USE_LOCAL_API:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer
        server = TelegramAPIServer.from_base(f"http://{BOT_API_SERVER}:{BOT_API_PORT or 8081}", is_local=True)
        bot_kwargs["session"] = AiohttpSession(api=server)
        log.info("Using Local Bot API: %s:%s", BOT_API_SERVER, BOT_API_PORT)

    bot = Bot(**bot_kwargs)
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(ThrottleMiddleware(rate=0.7))
    dp.callback_query.middleware(ThrottleMiddleware(rate=0.4))

    # Routers (admin first to avoid overlap)
    dp.include_router(admin_handler.router)
    dp.include_router(user_handler.router)

    # Fallback handler for non-admin /admin attempt
    from aiogram import Router, F
    from aiogram.filters import Command
    fallback = Router()

    @fallback.message(Command("admin"))
    async def _admin_denied(message):
        from bot.config import is_admin
        if not is_admin(message.from_user.id):
            await message.answer("⛔ این دستور فقط برای ادمین‌هاست.")

    dp.include_router(fallback)

    await on_startup(bot)

    # Background cleanup
    asyncio.create_task(periodic_cleanup())

    log.info("Starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutdown requested.")
