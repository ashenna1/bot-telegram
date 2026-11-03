"""
User-facing handlers: /start, /help, link processing
"""
import asyncio
import logging
import os
import re
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, ReactionTypeEmoji
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.config import BOT_NAME, ADMIN_IDS, DATABASE_PATH
from bot.db import get_setting, upsert_user, get_user, check_rate_limit, log_download, count_users
from bot.utils.links import find_first_supported_url, platform_emoji, platform_name_fa
from bot.utils.helpers import build_caption, fmt_size, fmt_duration, truncate
from bot.utils.downloader import download_media, cleanup_tmp
from bot.utils.force_join import check_user_joined
from bot.keyboards.inline import force_join_kb, after_video_kb

log = logging.getLogger("user")
router = Router()

# ---- Helpers ----

async def try_set_reaction(bot: Bot, chat_id: int, message_id: int):
    """
    Immediate 🙄 reaction per spec.
    Bot API allow-list is limited; many clients reject 🙄 for bots.
    We try 🙄 first, then fallback to 🤔 (allowed), then silently ignore if not permitted.
    Uses set_message_reaction (requires bot to have rights in group; in PM always works).
    """
    for emoji in ("🙄", "🤔"):
        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
            log.info("Set reaction %s on %s/%s", emoji, chat_id, message_id)
            return emoji
        except TelegramBadRequest as e:
            # Retry with fallback emoji if first fails due to not allowed
            txt = str(e).lower()
            if "not allowed" in txt or "reaction" in txt:
                continue
            log.warning("set_reaction failed: %s", e)
            return None
        except Exception as e:
            log.warning("set_reaction error: %s", e)
            return None
    return None

async def clear_reaction(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[])
    except Exception:
        pass

# ---- Commands ----

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    welcome = await get_setting("welcome_message", "")
    if not welcome:
        from bot.config import DEFAULT_SETTINGS
        welcome = DEFAULT_SETTINGS["welcome_message"]
    welcome = welcome.format(name=message.from_user.first_name or "دوست")
    me = await bot.get_me()
    # Maintenance notice
    if await get_setting("maintenance_mode", "0") == "1":
        if message.from_user.id not in ADMIN_IDS:
            txt = await get_setting("maintenance_text", "")
            await message.answer(txt)
            return
    await message.answer(
        welcome + f"\n\n🤖 @{me.username}\n📚 /help — راهنما",
        disable_web_page_preview=True,
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📚 <b>راهنمای MediODL</b>\n\n"
        "فقط لینک بفرست — بقیه با ما:\n"
        "• 🔴 <b>یوتیوب</b> — youtube.com / youtu.be / Shorts\n"
        "• 📸 <b>اینستاگرام</b> — پست / ریلز / استوری\n"
        "• 🎵 <b>تیک‌تاک</b> — tiktok.com / vm.tiktok.com\n\n"
        "هر لینک = <b>ویدیو با بالاترین کیفیت + فایل صوتی جدا</b> 🎬🎧\n\n"
        "💡 اگر ویدیو بالای 50MB بود، ربات با Local Bot API تا 2GB را هم می‌فرستد (نصب خودکار در سرور).\n"
        "🆘 مشکلی بود؟ به ادمین پیام بده.",
        parse_mode="HTML",
    )

@router.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong — ربات فعاله!")

@router.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery, bot: Bot):
    ok, missing = await check_user_joined(bot, callback.from_user.id)
    if ok:
        await callback.answer("✅ عضویت تأیید شد! حالا دوباره لینک را بفرست.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("❌ هنوز در همه کانال‌ها عضو نشدی.", show_alert=True)

# ---- Main link handler ----

# Regex to quick-filter non-links
_URL_LIKE = re.compile(r"https?://")

@router.message(F.text & F.text.regexp(_URL_LIKE))
async def handle_link(message: Message, bot: Bot):
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    url, platform = find_first_supported_url(text)
    if not url:
        # Not a supported platform — ignore silently or hint
        # But if it looks like a link, give friendly hint
        if "instagram.com" in text.lower() or "tiktok.com" in text.lower() or "youtu" in text.lower():
            await message.answer(
                "❓ لینک نامعتبر به نظر می‌رسد. لطفاً لینک مستقیم پست/ویدیو را بفرست.\n"
                "مثال:\n<code>https://www.youtube.com/watch?v=...</code>\n"
                "<code>https://www.instagram.com/reel/...</code>\n"
                "<code>https://www.tiktok.com/@.../video/...</code>",
                parse_mode="HTML",
            )
        return

    # ---- Maintenance ----
    if await get_setting("maintenance_mode", "0") == "1" and user_id not in ADMIN_IDS:
        txt = await get_setting("maintenance_text", "")
        await message.answer(txt)
        return

    # ---- Ban check ----
    row = await get_user(user_id)
    if row and len(row) > 6 and row[6] == 1:  # is_banned
        await message.answer("🚫 شما از ربات مسدود شده‌اید.")
        return

    # Upsert user
    await upsert_user(user_id, message.from_user.username, message.from_user.full_name)

    # ---- Rate limit ----
    max_per_hour = int(await get_setting("rate_limit_per_hour", "20") or 20)
    allowed, wait = await check_rate_limit(user_id, max_per_hour)
    if not allowed:
        mins = wait // 60 or 1
        await message.answer(f"⏳ محدودیت درخواست — لطفاً حدود {mins} دقیقه دیگر دوباره تلاش کن.")
        return

    # ---- Force-join ----
    force_enabled = await get_setting("force_join_enabled", "0")
    if force_enabled == "1":
        ok, missing = await check_user_joined(bot, user_id)
        if not ok:
            kb = force_join_kb(missing)
            await message.answer(
                "🔒 برای استفاده از ربات لطفاً ابتدا در کانال(های) زیر عضو شو، سپس «بررسی عضویت» را بزن:",
                reply_markup=kb,
            )
            return

    # ---- Reaction 🙄 ----
    await try_set_reaction(bot, message.chat.id, message.message_id)

    # ---- Status message ----
    emoji = platform_emoji(platform)
    pname = platform_name_fa(platform)
    status_msg = await message.answer(
        f"{emoji} <b>در حال پردازش لینک {pname}...</b>\n"
        f"🔗 <code>{truncate(url, 80)}</code>\n\n"
        f"⏳ در حال دریافت اطلاعات ویدیو — لطفاً کمی صبر کن...",
        parse_mode="HTML",
    )

    # ---- Download ----
    tmp_info = None
    try:
        # update status
        await status_msg.edit_text(
            f"{emoji} <b>در حال دانلود با بهترین کیفیت...</b> ⬇️\n"
            f"🎬 {pname} — در حال آماده‌سازی ویدیو و صدای جداگانه 🎧\n"
            f"⏳ این مرحله بسته به حجم ویدیو ممکن است تا 1-2 دقیقه طول بکشد.",
            parse_mode="HTML",
        )

        max_h = int(await get_setting("max_video_height", "1080") or 1080)
        result = await download_media(url, platform, max_height=max_h)
        tmp_info = result  # for cleanup

        meta = result["meta"]
        video_path: Path = result["video_path"]
        audio_path: Path | None = result["audio_path"]

        # Check size vs Bot API limit (50MB official, higher with local API)
        max_upload = int(await get_setting("max_upload_mb", "2000") or 2000)
        # We treat official limit as 50 unless BOT_API_SERVER set
        from bot.config import USE_LOCAL_API
        effective_limit_mb = max_upload if USE_LOCAL_API else 50
        vsize_mb = video_path.stat().st_size / (1024 * 1024)

        # Build caption
        caption_template = await get_setting("caption_template", "")
        me = await bot.get_me()
        caption = build_caption(meta, caption_template, me.username or "")

        # ---- Send Video ----
        show_audio = await get_setting("show_audio_separately", "1") == "1"

        # If too large for upload, notify and skip video upload (or send as document chunk? not possible)
        if vsize_mb > effective_limit_mb:
            await status_msg.edit_text(
                f"⚠️ <b>ویدیو خیلی حجیم است ({vsize_mb:.1f}MB)</b>\n"
                f"سقف آپلود مستقیم ربات {effective_limit_mb}MB است.\n"
                f"برای فایل‌های تا 2GB، ادمین باید Local Bot API را فعال کند (راهنمای نصب داخل ریپو موجود است).\n\n"
                f"🎬 <b>{truncate(meta.get('title','') , 80)}</b>\n"
                f"⏱️ {fmt_duration(meta.get('duration'))} | 👁️ {meta.get('view_count','—')}",
                parse_mode="HTML",
            )
            # Try to send audio if small enough
            if audio_path and audio_path.exists() and (audio_path.stat().st_size / (1024*1024) <= effective_limit_mb):
                try:
                    await bot.send_audio(
                        chat_id=message.chat.id,
                        audio=FSInputFile(audio_path),
                        title=(meta.get("title") or "audio")[:60],
                        performer=meta.get("uploader") or "",
                        duration=int(meta.get("duration") or 0),
                        caption=f"🎧 صدای جدا — {meta.get('title','')[:100]}",
                        reply_to_message_id=message.message_id,
                    )
                except Exception:
                    pass
            await log_download(user_id, platform, url, meta.get("title",""), int(meta.get("duration") or 0), int(video_path.stat().st_size), success=0, error=f"too_large_{vsize_mb:.1f}MB")
            await clear_reaction(bot, message.chat.id, message.message_id)
            return

        # Small delay to avoid flood
        await asyncio.sleep(0.3)
        try:
            await status_msg.edit_text("📤 در حال ارسال ویدیو... 🚀", parse_mode="HTML")
        except Exception:
            pass

        # Determine send method: video vs document (preserve quality)
        # Use send_video for preview, fallback to document
        video_sent = False
        try:
            await bot.send_video(
                chat_id=message.chat.id,
                video=FSInputFile(video_path),
                caption=caption[:1024],
                parse_mode="HTML",
                supports_streaming=True,
                duration=int(meta.get("duration") or 0),
                width=int(meta.get("width") or 0) or None,
                height=int(meta.get("height") or 0) or None,
                reply_to_message_id=message.message_id,
                reply_markup=after_video_kb(platform, url),
            )
            video_sent = True
        except TelegramBadRequest as e:
            log.warning("send_video failed, trying document: %s", e)
            try:
                await bot.send_document(
                    chat_id=message.chat.id,
                    document=FSInputFile(video_path, filename=f"{Path(video_path).stem}.mp4"),
                    caption=caption[:1024],
                    parse_mode="HTML",
                    reply_to_message_id=message.message_id,
                    reply_markup=after_video_kb(platform, url),
                )
                video_sent = True
            except Exception as e2:
                raise RuntimeError(f"خطا در ارسال ویدیو: {e2}") from e2

        # ---- Send Audio separately (required spec) ----
        if show_audio and audio_path and audio_path.exists():
            asize_mb = audio_path.stat().st_size / (1024*1024)
            if asize_mb <= effective_limit_mb:
                try:
                    await asyncio.sleep(0.4)
                    await bot.send_audio(
                        chat_id=message.chat.id,
                        audio=FSInputFile(audio_path),
                        title=(meta.get("title") or "audio")[:64],
                        performer=meta.get("uploader") or meta.get("channel") or "",
                        duration=int(meta.get("duration") or 0),
                        caption=f"🎧 <b>فایل صوتی جدا</b>\n🎬 {truncate(meta.get('title',''), 60)}\n⏱️ {fmt_duration(meta.get('duration'))}",
                        parse_mode="HTML",
                        reply_to_message_id=message.message_id,
                    )
                except TelegramBadRequest:
                    # fallback as document
                    try:
                        await bot.send_document(
                            chat_id=message.chat.id,
                            document=FSInputFile(audio_path),
                            caption=f"🎧 صدای ویدیو — {truncate(meta.get('title',''), 80)}",
                            reply_to_message_id=message.message_id,
                        )
                    except Exception:
                        pass
                except Exception as e:
                    log.warning("send_audio failed: %s", e)

        # ---- Ad injection (every N downloads) ----
        try:
            from bot.db import get_active_ad_for_user, count_users
            # download count of user
            row2 = await get_user(user_id)
            dl_count = row2[7] if row2 and len(row2) > 7 else 1
            # Use downloads as counter
            active_ad = await get_active_ad_for_user(dl_count)
            if active_ad:
                _aid, atext, aphoto, abtn_text, abtn_url, _ac, _ev = active_ad
                kb_ad = None
                if abtn_text and abtn_url:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb_ad = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=abtn_text[:30], url=abtn_url)]])
                if aphoto:
                    try:
                        await bot.send_photo(chat_id=message.chat.id, photo=aphoto, caption=atext[:1000], reply_markup=kb_ad, parse_mode="HTML")
                    except Exception:
                        await bot.send_message(chat_id=message.chat.id, text=atext[:3000], reply_markup=kb_ad, parse_mode="HTML", disable_web_page_preview=True)
                else:
                    await bot.send_message(chat_id=message.chat.id, text=atext[:3000], reply_markup=kb_ad, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

        # ---- Final status ---
        try:
            await status_msg.delete()
        except Exception:
            try:
                await status_msg.edit_text("✅ انجام شد!", parse_mode="HTML")
            except Exception:
                pass

        await log_download(user_id, platform, url, meta.get("title",""), int(meta.get("duration") or 0), int(video_path.stat().st_size), success=1)
        await clear_reaction(bot, message.chat.id, message.message_id)

    except RuntimeError as e:
        err = str(e)
        try:
            await status_msg.edit_text(err, parse_mode="HTML")
        except Exception:
            await message.answer(err, parse_mode="HTML")
        await log_download(user_id, platform, url, "", 0, 0, success=0, error=err[:400])
        await clear_reaction(bot, message.chat.id, message.message_id)

    except Exception as e:
        log.exception("Unhandled download error for %s: %s", url, e)
        try:
            await status_msg.edit_text(
                "❌ خطای غیرمنتظره در پردازش لینک.\n"
                "لطفاً دوباره تلاش کن و اگر ادامه داشت به ادمین اطلاع بده.\n"
                f"<code>{truncate(str(e), 300)}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await log_download(user_id, platform, url, "", 0, 0, success=0, error=str(e)[:400])
        await clear_reaction(bot, message.chat.id, message.message_id)

    finally:
        # cleanup tmp after a short delay (so uploads finish)
        if tmp_info and tmp_info.get("tmp_dir"):
            # delay cleanup 60s to ensure file handles closed
            async def _d():
                await asyncio.sleep(60)
                cleanup_tmp(tmp_info["tmp_dir"])
            asyncio.create_task(_d())
