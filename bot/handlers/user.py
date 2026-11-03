"""
User-facing handlers: start, help, captcha, quality selection, link processing, fun
"""
import asyncio
import logging
import re
import time
import uuid
import json
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, ReactionTypeEmoji
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest

from bot.config import BOT_NAME, ADMIN_IDS, DATABASE_PATH, LOG_LEVEL
from bot.db import (
    get_setting, upsert_user, get_user, check_rate_limit, log_download,
    set_captcha, get_captcha, clear_captcha, inc_captcha_attempt, set_verified,
    save_pending, get_pending, delete_pending, queue_auto_delete,
    check_flood_per_min, add_warning
)
from bot.utils.links import find_first_supported_url, platform_emoji, platform_name_fa, is_audio_only_platform
from bot.utils.helpers import build_caption, fmt_size, fmt_duration, truncate, random_compliment, random_fact, random_joke, fun_greeting
from bot.utils.captcha import generate_captcha, captcha_expired
from bot.utils.downloader import download_media
from bot.utils.force_join import check_user_joined
from bot.keyboards.inline import force_join_kb, after_video_kb, captcha_kb, quality_kb

log = logging.getLogger("user")
router = Router()

# ---- Small in-memory cache for pending quality tokens (also in DB)
_pending_cache: dict[str, dict] = {}

# ---- Helpers ----
async def try_set_reaction(bot: Bot, chat_id: int, message_id: int):
    for emoji in ("🙄", "🤔"):
        try:
            await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[ReactionTypeEmoji(emoji=emoji)])
            return emoji
        except TelegramBadRequest as e:
            if "not allowed" in str(e).lower() or "reaction" in str(e).lower():
                continue
            return None
        except Exception:
            return None
    return None

async def clear_reaction(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[])
    except Exception:
        pass

async def is_user_verified(user_id: int) -> bool:
    # If captcha disabled globally, everyone verified
    if (await get_setting("captcha_enabled", "0")) != "1":
        return True
    row = await get_user(user_id)
    if not row:
        return False
    # users schema: ... is_verified at index 8 (0-based: user_id,username,fullname,lang,joined_at,last_seen,is_banned,downloads,is_verified,...)
    # But to be robust, fetch column names
    try:
        # row tuple length 10+; is_verified is 8
        return bool(row[8]) if len(row) > 8 else True
    except Exception:
        return True

async def need_captcha(user_id: int) -> bool:
    if (await get_setting("captcha_enabled", "0")) != "1":
        return False
    return not await is_user_verified(user_id)

async def send_captcha_challenge(message: Message, user_id: int):
    mode = await get_setting("captcha_mode", "emoji")
    timeout = int(await get_setting("captcha_timeout_sec", "120") or 120)
    q_text, answer, options = generate_captcha(mode)
    await set_captcha(user_id, q_text, answer)
    kb = captcha_kb(options, answer)
    await message.answer(q_text, parse_mode="HTML", reply_markup=kb)

# ---- Commands ----
@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    # Maintenance
    if await get_setting("maintenance_mode", "0") == "1" and message.from_user.id not in ADMIN_IDS:
        await message.answer(await get_setting("maintenance_text", ""))
        return
    # Log new user (notify admins)
    row = await get_user(message.from_user.id)
    is_new = False
    if row:
        # If joined_at == last_seen and very recent => new
        try:
            if row[4] and row[5] and abs(row[4] - row[5]) < 5:
                is_new = True
        except Exception:
            pass
    if is_new:
        try:
            from bot.utils.logger import log_new_user
            await log_new_user(bot, message.from_user.id, message.from_user.username, message.from_user.full_name)
        except Exception:
            pass
    # Captcha
    if await need_captcha(message.from_user.id):
        await send_captcha_challenge(message, message.from_user.id)
        return

    welcome = await get_setting("welcome_message", "")
    if not welcome:
        from bot.config import DEFAULT_SETTINGS
        welcome = DEFAULT_SETTINGS["welcome_message"]
    welcome = welcome.format(name=message.from_user.first_name or "دوست", bot_name=BOT_NAME)
    # Fun mode
    if (await get_setting("fun_mode", "1")) == "1" and (await get_setting("fun_greeting_enabled", "1")) == "1":
        welcome = fun_greeting(message.from_user.first_name or "دوست") + "\n\n" + welcome

    me = await bot.get_me()
    # Fun quick buttons
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 فکت باحال", callback_data="fun:fact"), InlineKeyboardButton(text="😂 جوک", callback_data="fun:joke")],
        [InlineKeyboardButton(text="📚 راهنما", callback_data="fun:help")],
    ])
    await message.answer(welcome + f"\n\n🤖 @{me.username} — فقط لینک بفرست! 🚀", parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📚 <b>راهنمای MediGo (ویدا‌ن)</b> 🎬\n\n"
        "فقط لینک بفرست — بقیه با ما 😎:\n"
        "• 🔴 یوتیوب (ویدیو/Shorts)\n"
        "• 📸 اینستاگرام (پست/ریلز/استوری)\n"
        "• 🎵 تیک‌تاک\n"
        "• 📌 پینترست\n"
        "• 🐦 توییتر/X\n"
        "• 👥 فیسبوک\n"
        "• 🎧 ساندکلاد\n"
        "• 💚 اسپاتیفای (جستجوی خودکار)\n"
        "• 🧵 تردز\n\n"
        "هر لینک = <b>ویدیو باکیفیت + صدای جدا</b> 🎬🎧\n"
        "✨ می‌تونی کیفیت رو هم انتخاب کنی: 480/720/1080/فقط صدا\n"
        "💡 ویدیوهای بالای 50MB با Local Bot API تا 2GB هم میاد!\n"
        "😍 حالت فان فعاله — دکمه 🎲 رو بزن!\n",
        parse_mode="HTML",
    )

@router.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer(f"🏓 پونگ! ربات {BOT_NAME} فعاله — حالت فان {'روشن 😎' if await get_setting('fun_mode','1')=='1' else 'خاموش'}")

# ---- Captcha callback ----
@router.callback_query(F.data.startswith("captcha:"))
async def cb_captcha(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    picked = callback.data.split(":", 1)[1]
    state = await get_captcha(user_id)
    if not state:
        await callback.answer("⏰ کپچا منقضی شد، /start بزن", show_alert=True)
        return
    question, answer, attempts, created_at = state
    timeout = int(await get_setting("captcha_timeout_sec", "120") or 120)
    if captcha_expired(created_at, timeout):
        await clear_captcha(user_id)
        await callback.answer("⏰ زمان کپچا تمام شد! دوباره /start بزن", show_alert=True)
        try: await callback.message.edit_text("⏰ کپچا منقضی شد. /start بزن تا یکی جدید بگیری.", parse_mode="HTML")
        except Exception: pass
        return
    if picked == answer:
        await set_verified(user_id, True)
        await clear_captcha(user_id)
        await callback.answer("✅ تأیید شد! حالا می‌تونی دانلود کنی 🎉", show_alert=True)
        try: await callback.message.edit_text("✅ عالی شد! تأیید شدی — حالا لینک بفرست تا برات دانلود کنم 🚀", parse_mode="HTML")
        except Exception: pass
        # Send welcome after verify
        welcome = await get_setting("welcome_message", "")
        from bot.config import DEFAULT_SETTINGS
        if not welcome:
            welcome = DEFAULT_SETTINGS["welcome_message"]
        welcome = welcome.format(name=callback.from_user.first_name or "دوست", bot_name=BOT_NAME)
        me = await bot.get_me()
        await bot.send_message(callback.message.chat.id, welcome + f"\n\n🤖 @{me.username}", parse_mode="HTML")
    else:
        await inc_captcha_attempt(user_id)
        new_state = await get_captcha(user_id)
        att = new_state[2] if new_state else attempts + 1
        if att >= 3:
            await clear_captcha(user_id)
            await callback.answer("❌ ۳ بار اشتباه — ۱ دقیقه صبر کن و /start بزن", show_alert=True)
            try: await callback.message.edit_text("❌ کپچا ناموفق. لطفاً ۱ دقیقه بعد /start بزن.", parse_mode="HTML")
            except Exception: pass
        else:
            await callback.answer(f"❌ اشتباه بود! {3-att} فرصت دیگه داری — دوباره سعی کن", show_alert=True)

# ---- Fun ----
@router.callback_query(F.data == "fun:thanks")
async def cb_thanks(callback: CallbackQuery):
    await callback.answer(random_compliment(), show_alert=True)

@router.callback_query(F.data == "fun:fact")
async def cb_fact(callback: CallbackQuery):
    await callback.message.answer(random_fact(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "fun:joke")
async def cb_joke(callback: CallbackQuery):
    await callback.message.answer(random_joke(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "fun:help")
async def cb_fun_help(callback: CallbackQuery):
    await callback.message.answer(
        "📚 فقط لینک بفرست:\n"
        "• یوتیوب/اینستا/تیک‌تاک/پینترست/توییتر/فیسبوک/ساندکلاد/اسپاتیفای/تردز\n"
        "حالت فان روشنه 😎 — هر دانلود یه پیام باحال هم می‌گیری!",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery, bot: Bot):
    from bot.utils.force_join import check_user_joined as _check
    ok, missing = await _check(bot, callback.from_user.id)
    if ok:
        await callback.answer("✅ عضویت تأیید شد! لینک رو بفرست.", show_alert=True)
        try: await callback.message.delete()
        except: pass
    else:
        await callback.answer("❌ هنوز عضو نشدی.", show_alert=True)

# ---- Quality selection callback ----
@router.callback_query(F.data.startswith("q:"))
async def cb_quality(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer()
        return
    quality, token = parts[1], parts[2]
    if quality == "cancel":
        await delete_pending(token)
        _pending_cache.pop(token, None)
        await callback.answer("لغو شد")
        try: await callback.message.edit_text("❌ دانلود لغو شد.")
        except: pass
        return
    # Fetch pending
    pending = await get_pending(token)
    cached = _pending_cache.get(token)
    if not pending and not cached:
        await callback.answer("⏰ منقضی شد — دوباره لینک بفرست", show_alert=True)
        return
    if pending:
        uid, url, platform, meta_json = pending
        meta = json.loads(meta_json) if meta_json else {}
    else:
        url = cached["url"]; platform = cached["platform"]; meta = cached["meta"]; uid = cached["user_id"]

    # Map quality to max_height / audio_only
    await callback.answer(f"⏳ در حال دانلود {quality}...")
    try: await callback.message.edit_text(f"⏳ در حال دانلود کیفیت <b>{quality}</b>... لطفاً صبر کن ⏬", parse_mode="HTML")
    except: pass

    max_h = {"480": 480, "720": 720, "1080": 1080}.get(quality, 1080)
    audio_only = (quality == "audio")
    both_audio = False
    if quality == "both":
        max_h = int(await get_setting("max_video_height", "1080") or 1080)
        both_audio = True

    # Actually download now with chosen quality
    await do_download(callback.message, bot, url, platform, quality_token=token, max_h=max_h, audio_only=audio_only, both_audio=both_audio, meta_probe=meta, status_msg=callback.message, original_msg_id=callback.message.message_id)

async def do_download(trigger_msg: Message, bot: Bot, url: str, platform: str, quality_token: str | None = None, max_h: int | None = None, audio_only: bool = False, both_audio: bool = False, meta_probe: dict | None = None, status_msg: Message | None = None, original_msg_id: int | None = None):
    """Core download logic used by both direct and quality-picked paths."""
    user_id = trigger_msg.chat.id if hasattr(trigger_msg, 'chat') else trigger_msg.from_user.id
    # For callback path, chat.id is correct
    # Need original user id
    # In pending we have uid
    if quality_token:
        pend = await get_pending(quality_token)
        if pend:
            user_id = pend[0]
            # Also get username for logging
            row = await get_user(user_id)
            username = row[1] if row and len(row) > 1 else None
        else:
            username = None
    else:
        # Direct path: user_id from trigger_msg
        try:
            user_id = trigger_msg.from_user.id if hasattr(trigger_msg, 'from_user') and trigger_msg.from_user else trigger_msg.chat.id
            username = trigger_msg.from_user.username if hasattr(trigger_msg, 'from_user') and trigger_msg.from_user else None
        except:
            username = None

    # Use pending user_id as author for replies
    chat_id = trigger_msg.chat.id

    # For direct link handler we already have status_msg, here reuse
    # Determine effective limit
    max_upload = int(await get_setting("max_upload_mb", "2000") or 2000)
    from bot.config import USE_LOCAL_API
    effective_limit_mb = max_upload if USE_LOCAL_API else 50

    # If we have a message from quality picker, use it as status_msg
    # else it was created in handle_link
    # We'll need to edit it throughout

    tmp_info = None
    try:
        max_height = max_h or int(await get_setting("max_video_height", "1080") or 1080)
        result = await download_media(url, platform, max_height=max_height, audio_only=audio_only)
        tmp_info = result
        meta = result["meta"]
        video_path = result.get("video_path")
        audio_path = result.get("audio_path")

        # Audio-only platforms
        if audio_only or (platform in ("soundcloud", "spotify") and video_path is None):
            if not audio_path or not audio_path.exists():
                raise RuntimeError("❌ فایل صوتی یافت نشد.")
            asize = audio_path.stat().st_size / (1024*1024)
            if asize > effective_limit_mb:
                await status_msg.edit_text(f"⚠️ فایل صوتی خیلی بزرگه ({asize:.1f}MB) — سقف {effective_limit_mb}MB", parse_mode="HTML")
                return
            await bot.send_audio(chat_id=chat_id, audio=FSInputFile(audio_path), title=(meta.get("title") or "audio")[:64], performer=meta.get("uploader") or "", duration=int(meta.get("duration") or 0), caption=f"🎧 {truncate(meta.get('title',''),80)}\n{random_compliment()}", parse_mode="HTML")
            if both_audio:
                pass  # already sent
            # Auto delete
            auto_h = float(await get_setting("auto_delete_hours", "0") or 0)
            # queue already via send? we need message ids
            # We'll approximate: not deleting audio for now unless we capture ids
            try: await status_msg.delete()
            except: pass
            await log_download(user_id, platform, url, meta.get("title",""), int(meta.get("duration") or 0), int(audio_path.stat().st_size), success=1)
            try:
                from bot.utils.logger import log_download_event
                await log_download_event(bot, user_id, username, platform, meta.get("title",""), True, fmt_size(audio_path.stat().st_size))
            except: pass
            return

        # Video + audio
        if not video_path or not video_path.exists():
            raise RuntimeError("❌ ویدیو یافت نشد.")
        vsize_mb = video_path.stat().st_size / (1024*1024)
        caption_template = await get_setting("caption_template", "")
        me = await bot.get_me()
        caption = build_caption(meta, caption_template, me.username or "")
        # Fun addition
        if (await get_setting("fun_mode", "1")) == "1":
            caption += f"\n\n{random_compliment()}"

        if vsize_mb > effective_limit_mb:
            await status_msg.edit_text(f"⚠️ <b>ویدیو خیلی حجیمه ({vsize_mb:.1f}MB)</b>\nسقف {effective_limit_mb}MB — برای 2GB لوکال API رو فعال کن.\n🎬 {truncate(meta.get('title',''),80)}", parse_mode="HTML")
            # try audio
            if audio_path and audio_path.exists() and audio_path.stat().st_size/(1024*1024) <= effective_limit_mb:
                try:
                    await bot.send_audio(chat_id=chat_id, audio=FSInputFile(audio_path), title=(meta.get("title") or "audio")[:60], duration=int(meta.get("duration") or 0), caption=f"🎧 صدای جدا — {meta.get('title','')[:100]}")
                except: pass
            await log_download(user_id, platform, url, meta.get("title",""), int(meta.get("duration") or 0), int(video_path.stat().st_size), success=0, error=f"too_large_{vsize_mb:.1f}MB")
            return

        await asyncio.sleep(0.2)
        try: await status_msg.edit_text("📤 در حال ارسال ویدیو... 🚀", parse_mode="HTML")
        except: pass

        # Send video
        sent_video_msg = None
        try:
            sent_video_msg = await bot.send_video(chat_id=chat_id, video=FSInputFile(video_path), caption=caption[:1024], parse_mode="HTML", supports_streaming=True, duration=int(meta.get("duration") or 0), width=int(meta.get("width") or 0) or None, height=int(meta.get("height") or 0) or None, reply_markup=after_video_kb(platform, url))
        except TelegramBadRequest:
            sent_video_msg = await bot.send_document(chat_id=chat_id, document=FSInputFile(video_path, filename=f"{Path(video_path).stem}.mp4"), caption=caption[:1024], parse_mode="HTML", reply_markup=after_video_kb(platform, url))

        # Auto delete queue
        auto_h = float(await get_setting("auto_delete_hours", "0") or 0)
        if auto_h > 0 and sent_video_msg:
            await queue_auto_delete(chat_id, sent_video_msg.message_id, auto_h)

        # Send audio separately
        show_audio = await get_setting("show_audio_separately", "1") == "1"
        sent_audio_msg = None
        if (show_audio or both_audio) and audio_path and audio_path.exists() and audio_path.stat().st_size/(1024*1024) <= effective_limit_mb:
            try:
                await asyncio.sleep(0.4)
                sent_audio_msg = await bot.send_audio(chat_id=chat_id, audio=FSInputFile(audio_path), title=(meta.get("title") or "audio")[:64], performer=meta.get("uploader") or "", duration=int(meta.get("duration") or 0), caption=f"🎧 <b>فایل صوتی جدا</b>\n🎬 {truncate(meta.get('title',''),60)}\n⏱️ {fmt_duration(meta.get('duration'))}", parse_mode="HTML")
                if auto_h > 0 and sent_audio_msg:
                    await queue_auto_delete(chat_id, sent_audio_msg.message_id, auto_h)
            except TelegramBadRequest:
                try:
                    sent_audio_msg = await bot.send_document(chat_id=chat_id, document=FSInputFile(audio_path), caption=f"🎧 صدای ویدیو — {truncate(meta.get('title',''),80)}")
                    if auto_h > 0 and sent_audio_msg:
                        await queue_auto_delete(chat_id, sent_audio_msg.message_id, auto_h)
                except: pass
            except Exception as e:
                log.warning("audio send fail %s", e)

        # Ad
        try:
            from bot.db import get_active_ad_for_user
            row2 = await get_user(user_id)
            dl_count = row2[7] if row2 and len(row2) > 7 else 1
            ad = await get_active_ad_for_user(dl_count)
            if ad:
                _aid, atext, aphoto, abtn_text, abtn_url, _ac, _ev = ad
                kb_ad = None
                if abtn_text and abtn_url:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb_ad = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=abtn_text[:30], url=abtn_url)]])
                if aphoto:
                    try: await bot.send_photo(chat_id=chat_id, photo=aphoto, caption=atext[:1000], reply_markup=kb_ad, parse_mode="HTML")
                    except: await bot.send_message(chat_id=chat_id, text=atext[:3000], reply_markup=kb_ad, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id=chat_id, text=atext[:3000], reply_markup=kb_ad, parse_mode="HTML")
        except: pass

        try: await status_msg.delete()
        except: pass
        await log_download(user_id, platform, url, meta.get("title",""), int(meta.get("duration") or 0), int(video_path.stat().st_size), success=1)
        try:
            from bot.utils.logger import log_download_event
            await log_download_event(bot, user_id, username, platform, meta.get("title",""), True, fmt_size(video_path.stat().st_size))
        except: pass
        if quality_token:
            await delete_pending(quality_token)
            _pending_cache.pop(quality_token, None)

    except RuntimeError as e:
        err = str(e)
        try: await status_msg.edit_text(err, parse_mode="HTML")
        except:
            try: await bot.send_message(chat_id=chat_id, text=err, parse_mode="HTML")
            except: pass
        await log_download(user_id, platform, url, "", 0, 0, success=0, error=err[:400])
        try:
            from bot.utils.logger import log_download_event
            await log_download_event(bot, user_id, None, platform, "", False, "", err[:200])
        except: pass
    except Exception as e:
        log.exception("download error %s %s", url, e)
        try: await status_msg.edit_text(f"❌ خطای غیرمنتظره\n<code>{truncate(str(e),300)}</code>", parse_mode="HTML")
        except: pass
        await log_download(user_id, platform, url, "", 0, 0, success=0, error=str(e)[:400])
    finally:
        if tmp_info and tmp_info.get("tmp_dir"):
            async def _d():
                await asyncio.sleep(60)
                from bot.utils.downloader import cleanup_tmp
                cleanup_tmp(tmp_info["tmp_dir"])
            asyncio.create_task(_d())

# ---- Main link handler ----
_URL_LIKE = re.compile(r"https?://")

@router.message(F.text & F.text.regexp(_URL_LIKE))
async def handle_link(message: Message, bot: Bot):
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    url, platform = find_first_supported_url(text)
    if not url:
        if any(k in text.lower() for k in ["instagram.com","tiktok.com","youtu","pinterest","twitter.com","x.com","facebook.com","soundcloud","spotify","threads.net"]):
            await message.answer("❓ لینک نامعتبر به نظر می‌رسه 😅\nمثال:\n<code>https://www.youtube.com/watch?v=...</code>\n<code>https://www.instagram.com/reel/...</code>\n<code>https://open.spotify.com/track/...</code>", parse_mode="HTML")
        return
    # Captcha gate
    if await need_captcha(user_id):
        await send_captcha_challenge(message, user_id)
        return
    # Maintenance
    if await get_setting("maintenance_mode","0")=="1" and user_id not in ADMIN_IDS:
        await message.answer(await get_setting("maintenance_text",""))
        return
    # Ban
    row = await get_user(user_id)
    if row and len(row) > 6 and row[6]==1:
        await message.answer("🚫 شما مسدود شدید 😢 — به ادمین پیام بده.")
        return
    await upsert_user(user_id, message.from_user.username, message.from_user.full_name)
    # Anti-spam per min
    if (await get_setting("antispam_enabled","1"))=="1":
        max_per_min = int(await get_setting("antispam_max_per_min","5") or 5)
        if not await check_flood_per_min(user_id, max_per_min):
            w = await add_warning(user_id)
            if w >= 3:
                ban_min = int(await get_setting("antispam_ban_minutes","10") or 10)
                await message.answer(f"🚫 به دلیل اسپم، {ban_min} دقیقه محدود شدی. آروم‌تر لینک بفرست 😅")
                # temporary ban: we set is_banned and schedule unban
                from bot.db import ban_user as _ban
                await _ban(user_id, True)
                # schedule unban
                async def _unban():
                    await asyncio.sleep(ban_min*60)
                    await _ban(user_id, False)
                    try: await bot.send_message(chat_id=user_id, text="✅ محدودیتت برداشته شد! دوباره می‌تونی دانلود کنی 🎉")
                    except: pass
                asyncio.create_task(_unban())
                try:
                    from bot.utils.logger import log_ban
                    await log_ban(bot, user_id, f"flood {max_per_min}/min, warnings {w}")
                except: pass
            else:
                await message.answer(f"🐢 یواش‌تر! خیلی تند لینک می‌فرستی — یه دقیقه صبر کن (اخطار {w}/3)")
            return
    # Rate limit per hour
    max_per_hour = int(await get_setting("rate_limit_per_hour","20") or 20)
    allowed, wait = await check_rate_limit(user_id, max_per_hour)
    if not allowed:
        await message.answer(f"⏳ سقف ساعتی پر شده — {wait//60 or 1} دقیقه دیگه امتحان کن 🙏")
        return
    # Force join
    if await get_setting("force_join_enabled","0")=="1":
        ok, missing = await check_user_joined(bot, user_id)
        if not ok:
            await message.answer("🔒 اول عضو کانال‌ها شو، بعدش برگرد پیشم 😊", reply_markup=force_join_kb(missing))
            return
    await try_set_reaction(bot, message.chat.id, message.message_id)
    emoji = platform_emoji(platform)
    pname = platform_name_fa(platform)

    # Quality selection vs auto
    use_quality = (await get_setting("quality_selection","1"))=="1" and not is_audio_only_platform(platform)
    if use_quality:
        # Need probe to show info
        status_msg = await message.answer(f"{emoji} <b>دارم لینک {pname} رو بررسی می‌کنم...</b> 🔍\n🔗 <code>{truncate(url,80)}</code>\n⏳ چند ثانیه صبر کن...", parse_mode="HTML")
        try:
            from bot.utils.downloader import probe_info as _probe
            meta = await _probe(url, platform)
            title = meta.get("title","")[:60]
            dur = fmt_duration(meta.get("duration"))
            thumb = meta.get("thumbnail")
            token = uuid.uuid4().hex[:8]
            # Save pending
            await save_pending(token, user_id, url, platform, json.dumps(meta, ensure_ascii=False))
            _pending_cache[token] = {"user_id": user_id, "url": url, "platform": platform, "meta": meta}
            # Friendly info + quality buttons
            fun_extra = f"\n\n{random_fact()}" if (await get_setting("fun_mode","1"))=="1" else ""
            await status_msg.edit_text(
                f"{emoji} <b>{title}</b>\n"
                f"📺 {platform_name_fa(platform)} | ⏱️ {dur} | 👁️ {fmt_size(meta.get('view_count')) if isinstance(meta.get('view_count'), int) else (meta.get('view_count') or '—')}\n"
                f"🎧 کیفیت مورد نظرت رو انتخاب کن:{fun_extra}",
                parse_mode="HTML",
                reply_markup=quality_kb(token, platform)
            )
            # Don't download yet; wait for callback
            return
        except Exception as e:
            # Fallback to auto download
            try: await status_msg.delete()
            except: pass
            # fall through to auto
            pass

    # Auto download (quality disabled or probe failed)
    status_msg = await message.answer(f"{emoji} <b>در حال پردازش لینک {pname}...</b>\n🔗 <code>{truncate(url,80)}</code>\n{random_compliment()} ⏳", parse_mode="HTML")
    await do_download(message, bot, url, platform, status_msg=status_msg, max_h=int(await get_setting("max_video_height","1080") or 1080))
