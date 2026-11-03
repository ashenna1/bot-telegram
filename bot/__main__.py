"""
MediODL Bot - Entrypoint with background tasks (auto-delete, daily report, pending cleanup)
"""
import asyncio
import logging
import sys
import time
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN, LOG_LEVEL, TMP_DIR, COOKIES_DIR, DATABASE_PATH
from bot.db import init_db, get_due_deletes, remove_delete_entry, cleanup_pending
from bot.utils.downloader import periodic_cleanup

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("main")
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)

async def on_startup(bot: Bot):
    me = await bot.get_me()
    log.info("Bot @%s (%s) started. DB=%s TMP=%s", me.username, me.id, DATABASE_PATH, TMP_DIR)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---- Background tasks ----
async def auto_delete_worker(bot: Bot):
    """Delete messages queued for auto-delete"""
    while True:
        try:
            due = await get_due_deletes(30)
            for eid, chat_id, message_id in due:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:
                    pass
                await remove_delete_entry(eid)
        except Exception as e:
            log.warning("auto_delete worker: %s", e)
        await asyncio.sleep(30)

async def pending_cleanup_worker():
    while True:
        try:
            await cleanup_pending()
        except: pass
        await asyncio.sleep(3600)

async def daily_report_worker(bot: Bot):
    """Send daily report at configured time"""
    last_sent = ""
    while True:
        try:
            from bot.db import get_setting, get_stats, count_users
            enabled = await get_setting("daily_report_enabled", "0")
            if enabled != "1":
                await asyncio.sleep(60)
                continue
            target_time = await get_setting("daily_report_time", "09:00")
            now_str = datetime.now().strftime("%H:%M")
            today_str = datetime.now().strftime("%Y-%m-%d")
            if now_str == target_time and last_sent != today_str:
                stats = await get_stats(1)
                total = await count_users()
                if stats:
                    row = stats[0]
                    txt = (
                        f"📅 <b>گزارش روزانه {today_str}</b>\n\n"
                        f"👥 کل کاربران: <b>{total}</b>\n"
                        f"📥 دانلود امروز: <b>{row[1]}</b>\n"
                        f"👤 ورودی جدید: <b>{row[2]}</b>\n"
                        f"📨 درخواست: <b>{row[3]}</b>\n\n"
                        f"🤖 @{ (await bot.get_me()).username }"
                    )
                else:
                    txt = f"📅 گزارش {today_str}: هنوز آماری نیست."
                from bot.config import ADMIN_IDS
                for aid in ADMIN_IDS:
                    try: await bot.send_message(aid, txt, parse_mode="HTML")
                    except: pass
                # Also to log channel
                ch = await get_setting("log_channel", "")
                if ch:
                    try: await bot.send_message(ch, txt, parse_mode="HTML")
                    except: pass
                last_sent = today_str
        except Exception as e:
            log.warning("daily_report: %s", e)
        await asyncio.sleep(45)

async def main():
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        print("❌ BOT_TOKEN تنظیم نشده! .env را چک کن.")
        sys.exit(1)
    await init_db()

    from bot.config import USE_LOCAL_API, BOT_API_SERVER, BOT_API_PORT
    bot_kwargs = {"token": BOT_TOKEN, "default": DefaultBotProperties(parse_mode=ParseMode.HTML)}
    if USE_LOCAL_API:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer
        server = TelegramAPIServer.from_base(f"http://{BOT_API_SERVER}:{BOT_API_PORT or 8081}", is_local=True)
        bot_kwargs["session"] = AiohttpSession(api=server)
        log.info("Using Local Bot API: %s:%s", BOT_API_SERVER, BOT_API_PORT)

    bot = Bot(**bot_kwargs)
    dp = Dispatcher(storage=MemoryStorage())
    from bot.middlewares.throttle import ThrottleMiddleware
    from bot.handlers import user as user_handler
    from bot.handlers import admin as admin_handler
    dp.message.middleware(ThrottleMiddleware(rate=0.7))
    dp.callback_query.middleware(ThrottleMiddleware(rate=0.4))
    dp.include_router(admin_handler.router)
    dp.include_router(user_handler.router)

    from aiogram import Router, F
    from aiogram.filters import Command
    fallback = Router()
    @fallback.message(Command("admin"))
    async def _admin_denied(message):
        from bot.config import is_admin
        if not is_admin(message.from_user.id):
            await message.answer("⛔ این دستور فقط برای ادمین‌هاست. 😅")
    dp.include_router(fallback)

    await on_startup(bot)
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(auto_delete_worker(bot))
    asyncio.create_task(pending_cleanup_worker())
    asyncio.create_task(daily_report_worker(bot))

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
