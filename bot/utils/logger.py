"""
Centralized event logger - sends to admin DM and/or log channel
Configurable via settings: log_channel, log_to_admin_dm, log_new_users, log_downloads, log_errors
"""
import logging
import html
from aiogram import Bot
from bot.config import ADMIN_IDS
from bot.db import get_setting

log = logging.getLogger("event_logger")

def _escape(s: str) -> str:
    return html.escape(str(s or ""))

async def send_log(bot: Bot, text: str, parse_mode: str = "HTML"):
    """Send to log_channel and/or admin DMs based on settings."""
    log_channel = (await get_setting("log_channel", "")).strip()
    to_admin = (await get_setting("log_to_admin_dm", "1")) == "1"

    # Truncate
    if len(text) > 4000:
        text = text[:4000] + "…"

    # To channel
    if log_channel:
        try:
            await bot.send_message(chat_id=log_channel, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception as e:
            log.warning("Log to channel %s failed: %s", log_channel, e)

    # To admins
    if to_admin:
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(chat_id=aid, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
            except Exception:
                pass

async def log_new_user(bot: Bot, user_id: int, username: str | None, fullname: str):
    if (await get_setting("log_new_users", "1")) != "1":
        return
    txt = (
        f"👤 <b>کاربر جدید</b> عضو شد!\n"
        f"🆔 <code>{user_id}</code>\n"
        f"👤 @{_escape(username) or '—'} | {_escape(fullname)}\n"
        f"🔗 <a href=\"tg://user?id={user_id}\">پیام به کاربر</a>"
    )
    await send_log(bot, txt)

async def log_download_event(bot: Bot, user_id: int, username: str | None, platform: str, title: str, success: bool, size: str = "", error: str = ""):
    if (await get_setting("log_downloads", "1")) != "1" and success:
        return
    if (await get_setting("log_errors", "1")) != "1" and not success:
        return
    status = "✅" if success else "❌"
    txt = (
        f"{status} <b>دانلود</b> | {platform}\n"
        f"👤 <code>{user_id}</code> @{_escape(username) or '—'}\n"
        f"🎬 {_escape(title)[:80]}\n"
        f"💾 {size} {('— ' + _escape(error)[:100]) if error else ''}"
    )
    await send_log(bot, txt)

async def log_ban(bot: Bot, user_id: int, reason: str):
    txt = f"🚫 <b>بن خودکار</b>\n🆔 <code>{user_id}</code>\n📌 { _escape(reason)}"
    await send_log(bot, txt)
