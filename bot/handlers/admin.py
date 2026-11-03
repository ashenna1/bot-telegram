"""
Admin panel - comprehensive + fun
Fix: settings now robust (try/except), plus captcha/antispam/logchan/autodel/stats/fun/update
"""
import time
import asyncio
import os
import re
import shutil
import subprocess
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import ADMIN_IDS, is_admin, DATABASE_PATH, TMP_DIR, COOKIES_DIR, COOKIES_YT, COOKIES_IG, COOKIES_TT, COOKIES_PIN, COOKIES_TW, COOKIES_FB, COOKIES_SC, COOKIES_SP, COOKIES_TH, VERSION
from bot.db import (
    get_all_settings, get_setting, set_setting,
    add_channel, remove_channel, toggle_channel, list_channels,
    add_ad, list_ads, toggle_ad, remove_ad,
    count_users, list_users, ban_user, get_user,
    get_stats, get_platform_stats, get_top_users,
)
from bot.keyboards.inline import (
    admin_main_kb, admin_settings_kb, admin_channels_kb, admin_ads_kb,
    admin_users_kb, admin_cookies_kb, back_to_main_kb, cancel_kb,
    admin_captcha_kb, admin_logchan_kb, admin_autodel_kb
)
from bot.utils.helpers import fmt_size, fmt_duration, escape_html, truncate

log = logging.getLogger("admin")
router = Router()
ADMIN_FILTER = F.from_user.id.in_(ADMIN_IDS)

class AdminState(StatesGroup):
    wait_value = State()
    wait_channel = State()
    wait_ad_text = State()
    wait_ad_button = State()
    wait_broadcast = State()
    wait_user_search = State()
    wait_cookie_upload = State()
    wait_log_channel = State()

def _is_admin(uid: int) -> bool:
    return is_admin(uid)

@router.message(ADMIN_FILTER, Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await show_main(message)

async def show_main(target: Message | CallbackQuery):
    try:
        settings = await get_all_settings()
        total_users = await count_users()
        stats = await get_stats(days=1)
        today = stats[0] if stats else ("—", 0, 0, 0)
        dl_today = today[1] if len(today) > 1 else 0
        req_today = today[3] if len(today) > 3 else 0
        txt = (
            "👑 <b>پنل مدیریت MediGo</b> 😎\n"
            f"🏷️ نسخه <code>{VERSION}</code> | ✨ حالت فان: {'روشن 🎉' if settings.get('fun_mode','1')=='1' else 'خاموش'}\n"
            f"👥 کاربران: <b>{total_users}</b> | 📥 امروز: <b>{dl_today}</b> | 📨 درخواست: <b>{req_today}</b>\n"
            f"⚙️ کیفیت: <b>{settings.get('max_video_height','1080')}p</b> | 🛠️ تعمیر: <b>{'ON' if settings.get('maintenance_mode')=='1' else 'OFF'}</b>\n"
            f"🛡️ کپچا: <b>{'ON' if settings.get('captcha_enabled','0')=='1' else 'OFF'}</b> | 🗑️ حذف: <b>{settings.get('auto_delete_hours','0')}h</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "یک گزینه رو انتخاب کن 👇"
        )
        kb = admin_main_kb()
        if isinstance(target, Message):
            await target.answer(txt, parse_mode="HTML", reply_markup=kb)
        else:
            try:
                await target.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                log.warning("show_main edit fail: %s", e)
                try: await target.message.answer(txt, parse_mode="HTML", reply_markup=kb)
                except: pass
            try: await target.answer()
            except: pass
    except Exception as e:
        log.exception("show_main error: %s", e)
        try:
            if isinstance(target, Message):
                await target.answer(f"❌ خطا در پنل: {e}", parse_mode="HTML")
            else:
                await target.message.answer(f"❌ خطا در پنل: {e}", parse_mode="HTML")
                await target.answer()
        except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:main")
async def cb_main(callback: CallbackQuery):
    await show_main(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:close")
async def cb_close(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    try: await callback.answer("بسته شد 👋")
    except: pass

# ---------- Stats (advanced) ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery):
    try:
        total = await count_users()
        verified = await count_users("WHERE is_verified=1") if "is_verified" in (await get_columns()) else total
        banned = await count_users("WHERE is_banned=1")
        stats7 = await get_stats(days=7)
        plat_stats = await get_platform_stats(days=7)
        top_users = await get_top_users(5, days=7)
        db_size = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
        tmp_size = sum(f.stat().st_size for f in TMP_DIR.glob("**/*") if f.is_file()) if TMP_DIR.exists() else 0

        lines = [
            "📊 <b>آمار پیشرفته</b> 📈\n",
            f"👥 کل: <b>{total}</b> | ✅ تأیید شده: <b>{verified}</b> | 🚫 بن: <b>{banned}</b>",
            f"💾 DB: <b>{fmt_size(db_size)}</b> | 📦 tmp: <b>{fmt_size(tmp_size)}</b>",
            "",
            "📅 <b>۷ روز اخیر:</b>",
            "<code>تاریخ        | دانلود | عضو+ | درخواست</code>",
        ]
        for row in stats7:
            lines.append(f"<code>{row[0]} | {row[1]:>6} | {row[2]:>6} | {row[3]:>7}</code>")
        if not stats7:
            lines.append("هنوز آماری نیست.")
        if plat_stats:
            lines.append("\n🎬 <b>تفکیک پلتفرم (۷ روز):</b>")
            for plat, cnt in plat_stats:
                lines.append(f"• {plat or '?'}: <b>{cnt}</b>")
        if top_users:
            lines.append("\n🏆 <b>برترین کاربران (۷ روز):</b>")
            for uid, cnt in top_users:
                lines.append(f"• <code>{uid}</code> — {cnt} دانلود")
        lines += ["", "💡 <code>mediodl status</code> برای جزئیات سرور"]
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_to_main_kb())
    except Exception as e:
        log.exception("stats error")
        try: await callback.message.edit_text(f"❌ خطا: {e}", reply_markup=back_to_main_kb())
        except: pass
    try: await callback.answer()
    except: pass

async def get_columns():
    import aiosqlite
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("PRAGMA table_info(users)") as cur:
                rows = await cur.fetchall()
                return [r[1] for r in rows]
    except: return []

# ---------- Settings ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery):
    try:
        s = await get_all_settings()
        txt = (
            "⚙️ <b>تنظیمات ربات</b>\n\n"
            "هر مورد رو لمس کن تا تغییرش بدی:\n"
            "• کیفیت، کپشن، خوش‌آمد، محدودیت‌ها\n"
            "• انتخاب کیفیت توسط کاربر\n"
        )
        await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_settings_kb(s))
    except Exception as e:
        log.exception("settings panel fail: %s", e)
        try: await callback.answer(f"خطا: {e}", show_alert=True)
        except: pass
        try: await callback.message.answer("⚙️ تنظیمات (fallback):", reply_markup=admin_settings_kb(await get_all_settings()))
        except: pass
        return
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:cfg:"))
async def cb_cfg(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 2)[2]
    try:
        s = await get_all_settings()
        cur = s.get(key, "")
        toggle_keys = ("show_audio_separately", "maintenance_mode", "captcha_enabled", "antispam_enabled", "fun_mode", "quality_selection", "log_to_admin_dm", "daily_report_enabled")
        if key in toggle_keys:
            new = "0" if cur == "1" else "1"
            await set_setting(key, new)
            try: await callback.answer(f"{key} → {new}")
            except: pass
            # Refresh correct panel
            ns = await get_all_settings()
            try:
                if key in ("captcha_enabled", "antispam_enabled", "fun_mode"):
                    await callback.message.edit_reply_markup(reply_markup=admin_captcha_kb(ns))
                elif key in ("log_to_admin_dm", "daily_report_enabled"):
                    await callback.message.edit_reply_markup(reply_markup=admin_logchan_kb(ns))
                else:
                    await callback.message.edit_reply_markup(reply_markup=admin_settings_kb(ns))
            except: pass
            return
        if key == "captcha_mode":
            modes = ["emoji", "math", "both"]
            try: idx = modes.index(cur)
            except: idx = 0
            new = modes[(idx + 1) % len(modes)]
            await set_setting(key, new)
            try: await callback.answer(f"کپچا: {new}")
            except: pass
            ns = await get_all_settings()
            try: await callback.message.edit_reply_markup(reply_markup=admin_captcha_kb(ns))
            except: pass
            return

        prompts = {
            "max_video_height": "🎞️ حداکثر کیفیت رو بفرست (مثلاً 1080):\nفعلی: <code>{cur}</code>",
            "caption_template": "📝 قالب کپشن:\n<code>{title}</code> <code>{uploader}</code> <code>{view_count}</code> <code>{like_count}</code> <code>{duration}</code> <code>{bot_username}</code>\n\nفعلی:\n<code>{cur}</code>",
            "welcome_message": "👋 پیام خوش‌آمد (از {name} و {bot_name} استفاده کن):\n\nفعلی:\n{cur}",
            "max_duration_sec": "⏱️ حداکثر طول ویدیو به ثانیه (3600=1ساعت):\nفعلی: <code>{cur}</code>",
            "rate_limit_per_hour": "🚦 سقف ساعتی هر کاربر:\nفعلی: <code>{cur}</code>",
            "maintenance_text": "🛠️ متن حالت تعمیر:\nفعلی:\n{cur}",
            "auto_delete_hours": "🗑️ حذف خودکار بعد چند ساعت؟ (0=خاموش):\nفعلی: <code>{cur}</code>",
            "log_channel": "📢 آیدی کانال لاگ رو بفرست (مثلاً @mylog یا -100...):\nفعلی: <code>{cur}</code>\nبرای حذف بنویس: clear",
            "daily_report_time": "📅 ساعت گزارش روزانه (HH:MM مثلاً 09:00):\nفعلی: <code>{cur}</code>",
        }
        prompt = prompts.get(key, f"مقدار جدید <code>{key}</code>:\nفعلی: <code>{cur}</code>")
        cur_esc = escape_html(cur[:800])
        prompt = prompt.format(cur=cur_esc if key != "welcome_message" else cur[:800])
        await state.set_state(AdminState.wait_value)
        await state.update_data(cfg_key=key)
        await callback.message.answer(prompt, parse_mode="HTML", reply_markup=cancel_kb())
        try: await callback.answer()
        except: pass
    except Exception as e:
        log.exception("cfg error %s", e)
        try: await callback.answer(f"خطا: {e}", show_alert=True)
        except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_value), F.text)
async def msg_cfg_value(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    key = data.get("cfg_key")
    val = message.text.strip()
    if key == "ad_every_pending":
        try: every = int(val)
        except: every = 3
        every = max(1, min(every, 100))
        await add_ad(data.get("ad_text",""), data.get("ad_photo"), data.get("ad_btn_text"), data.get("ad_btn_url"), show_every=every)
        await state.clear()
        await message.answer(f"✅ تبلیغ اضافه شد (هر {every} دانلود).", reply_markup=back_to_main_kb())
        return
    if key and key.startswith("dm_"):
        target_id = int(key.split("_",1)[1])
        try:
            await bot.send_message(chat_id=target_id, text=val, parse_mode="HTML")
            await message.answer(f"✅ به <code>{target_id}</code> ارسال شد.", parse_mode="HTML", reply_markup=back_to_main_kb())
        except Exception as e:
            await message.answer(f"❌ ارسال ناموفق: {e}", reply_markup=back_to_main_kb())
        await state.clear()
        return
    if not key:
        await state.clear()
        await message.answer("❌ وضعیت نامشخص. /admin بزن.", reply_markup=back_to_main_kb())
        return
    # validations
    if key in ("max_video_height", "max_duration_sec", "rate_limit_per_hour", "auto_delete_hours"):
        if key == "auto_delete_hours":
            try: float(val)
            except:
                await message.answer("❌ عدد بفرست (مثلاً 0 یا 1.5)")
                return
        else:
            if not val.isdigit():
                await message.answer("❌ فقط عدد بفرست:")
                return
    if key == "log_channel" and val.lower() == "clear":
        val = ""
    await set_setting(key, val)
    await state.clear()
    await message.answer(f"✅ <b>{key}</b> شد:\n<code>{escape_html(val[:500])}</code>", parse_mode="HTML", reply_markup=back_to_main_kb())

# ---------- Channels ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:channels")
async def cb_channels(callback: CallbackQuery):
    try:
        chs = await list_channels()
        enabled = await get_setting("force_join_enabled","0") == "1"
        txt = (
            "📢 <b>کانال‌های اجباری</b>\n\n"
            "کاربر تا عضو همه نشه دانلود نمی‌تونه بکنه.\n"
            f"وضعیت: <b>{'فعال ✅' if enabled else 'خاموش ⏸️'}</b>\nتعداد: {len(chs)}\n"
        )
        kb = admin_channels_kb(chs)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        toggle_btn = InlineKeyboardButton(text=f"{'⏸️ خاموش کردن' if enabled else '✅ روشن کردن'}", callback_data="adm:ch:toggle_force")
        new_kb = kb.inline_keyboard
        new_kb.insert(0, [toggle_btn])
        kb2 = InlineKeyboardMarkup(inline_keyboard=new_kb)
        await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=kb2)
    except Exception as e:
        log.exception("channels panel")
        try: await callback.message.answer(f"❌ {e}")
        except: pass
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:toggle_force")
async def cb_toggle_force(callback: CallbackQuery):
    cur = await get_setting("force_join_enabled","0")
    new = "0" if cur=="1" else "1"
    await set_setting("force_join_enabled", new)
    try: await callback.answer(f"{'فعال' if new=='1' else 'خاموش'} شد")
    except: pass
    await cb_channels(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:add")
async def cb_ch_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_channel)
    await callback.message.answer("➕ <b>افزودن کانال</b>\n<code>@my_channel</code>\nیا <code>@my_channel | https://t.me/+invite</code>", parse_mode="HTML", reply_markup=cancel_kb())
    try: await callback.answer()
    except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_channel), F.text)
async def msg_ch_add(message: Message, state: FSMContext):
    lines = [l.strip() for l in message.text.splitlines() if l.strip()]
    added=0
    for line in lines:
        invite=""
        if "|" in line:
            p1,p2=line.split("|",1)
            username=p1.strip(); invite=p2.strip()
        else: username=line.strip()
        if not username: continue
        await add_channel(username, invite_link=invite)
        added+=1
    await state.clear()
    await message.answer(f"✅ {added} کانال اضافه شد.", reply_markup=back_to_main_kb())
    if added: await message.answer("💡 ربات رو تو کانال ادمین کن تا چک دقیق بشه.", reply_markup=back_to_main_kb())

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:ch:"))
async def cb_ch_action(callback: CallbackQuery):
    parts=callback.data.split(":")
    if len(parts)<4:
        try: await callback.answer()
        except: pass
        return
    action,cid=parts[2],parts[3]
    if action=="noop":
        try: await callback.answer(f"کانال #{cid}")
        except: pass
        return
    if action=="toggle":
        await toggle_channel(int(cid))
        try: await callback.answer("تغییر کرد")
        except: pass
    elif action=="del":
        await remove_channel(int(cid))
        try: await callback.answer("حذف شد")
        except: pass
    await cb_channels(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:help")
async def cb_ch_help(callback: CallbackQuery):
    await callback.message.answer("💡 ربات رو ادمین کانال کن → یوزرنیم رو اضافه کن → با اکانت دوم تست کن.", parse_mode="HTML", reply_markup=back_to_main_kb())
    try: await callback.answer()
    except: pass

# ---------- Ads ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:ads")
async def cb_ads(callback: CallbackQuery):
    ads=await list_ads()
    txt=f"📣 <b>تبلیغات</b>\nتعداد: {len(ads)}\nهر N دانلود یک‌بار نمایش."
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_ads_kb(ads))
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:ad:add")
async def cb_ad_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_ad_text)
    await callback.message.answer("➕ <b>افزودن تبلیغ ۱/۳</b>\nمتن تبلیغ بفرست (HTML مجاز) یا عکس با کپشن", parse_mode="HTML", reply_markup=cancel_kb())
    try: await callback.answer()
    except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_ad_text), F.text | F.photo)
async def msg_ad_text(message: Message, state: FSMContext):
    text=message.caption or message.text or ""
    photo_id=message.photo[-1].file_id if message.photo else None
    await state.update_data(ad_text=text[:3000], ad_photo=photo_id)
    await state.set_state(AdminState.wait_ad_button)
    await message.answer("➕ <b>۲/۳ — دکمه (اختیاری)</b>\nفرمت: <code>متن | https://example.com</code>\nیا <code>skip</code>", parse_mode="HTML")

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_ad_button), F.text)
async def msg_ad_button(message: Message, state: FSMContext):
    data=await state.get_data()
    text=data.get("ad_text",""); photo_id=data.get("ad_photo")
    raw=message.text.strip()
    btn_text,btn_url=None,None
    if raw.lower() not in ("skip","رد","-","بدون"):
        if "|" in raw:
            a,b=raw.split("|",1)
            btn_text=a.strip()[:30]; btn_url=b.strip()
        else:
            btn_text=raw[:30]
    await state.update_data(ad_btn_text=btn_text, ad_btn_url=btn_url)
    await message.answer("➕ <b>۳/۳ — تناوب</b>\nهر چند دانلود؟ (عدد، پیش‌فرض 3)", parse_mode="HTML")
    await state.set_state(AdminState.wait_value)
    await state.update_data(cfg_key="ad_every_pending", ad_text=text, ad_photo=photo_id, ad_btn_text=btn_text, ad_btn_url=btn_url)

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:ad:"))
async def cb_ad_action(callback: CallbackQuery):
    parts=callback.data.split(":")
    if len(parts)<4:
        try: await callback.answer()
        except: pass
        return
    action,aid=parts[2],parts[3]
    if action=="noop":
        try: await callback.answer(f"تبلیغ #{aid}")
        except: pass
        return
    if action=="toggle":
        await toggle_ad(int(aid))
        try: await callback.answer("تغییر کرد")
        except: pass
    elif action=="del":
        await remove_ad(int(aid))
        try: await callback.answer("حذف شد")
        except: pass
    await cb_ads(callback)

# ---------- Users ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:users")
async def cb_users(callback: CallbackQuery):
    await callback.message.edit_text("👥 <b>کاربران</b>\nلیست ۲۰ تایی، جستجو، بن/آنبن", parse_mode="HTML", reply_markup=admin_users_kb())
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:users:"))
async def cb_users_sub(callback: CallbackQuery, state: FSMContext):
    sub=callback.data.split(":")[2]
    if sub=="list":
        offset=int(callback.data.split(":")[3]) if len(callback.data.split(":"))>3 else 0
        rows=await list_users(limit=20, offset=offset)
        if not rows:
            try: await callback.answer("کاربری نیست")
            except: pass
            return
        lines=["👥 <b>کاربران اخیر:</b>\n"]
        kb=InlineKeyboardBuilder()
        for r in rows:
            uid,uname,fname,dls,banned=r
            flag="🚫" if banned else "✅"
            lines.append(f"{flag} <code>{uid}</code> @{uname or '-'} — {escape_html(fname or '')} | 📥{dls}")
            kb.row(InlineKeyboardButton(text=f"{'آنبن' if banned else 'بن'} {uid}", callback_data=f"adm:usr:ban:{uid}"), InlineKeyboardButton(text=f"📨 {uid}", callback_data=f"adm:usr:msg:{uid}"))
        nav=[]
        if offset>0: nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"adm:users:list:{max(0,offset-20)}"))
        if len(rows)==20: nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"adm:users:list:{offset+20}"))
        if nav: kb.row(*nav)
        kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:users"))
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
        try: await callback.answer()
        except: pass
    elif sub=="search":
        await state.set_state(AdminState.wait_user_search)
        await callback.message.answer("🔍 آیدی یا @یوزرنیم بفرست:", reply_markup=cancel_kb())
        try: await callback.answer()
        except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_user_search), F.text)
async def msg_user_search(message: Message, state: FSMContext):
    q=message.text.strip().lstrip("@")
    rows=[]
    if q.isdigit():
        r=await get_user(int(q))
        rows=[r] if r else []
    else:
        import aiosqlite
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT user_id, username, fullname, downloads, is_banned FROM users WHERE username LIKE ? LIMIT 10", (f"%{q}%",)) as cur:
                rows=await cur.fetchall()
    await state.clear()
    if not rows or not rows[0]:
        await message.answer("❌ یافت نشد.", reply_markup=back_to_main_kb())
        return
    lines=[]; kb=InlineKeyboardBuilder()
    for r in rows:
        if not r: continue
        uid,uname,fname,dls,banned=r[0],r[1],r[2],r[3],r[4] if len(r)>=5 else 0
        flag="🚫" if banned else "✅"
        lines.append(f"{flag} <code>{uid}</code> @{uname or '-'} — {escape_html(fname or '')} | 📥{dls}")
        kb.row(InlineKeyboardButton(text=f"{'آنبن' if banned else 'بن'} {uid}", callback_data=f"adm:usr:ban:{uid}"), InlineKeyboardButton(text="📨 پیام", callback_data=f"adm:usr:msg:{uid}"))
    kb.row(InlineKeyboardButton(text="🔙 پنل", callback_data="adm:main"))
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:usr:"))
async def cb_usr_action(callback: CallbackQuery, state: FSMContext):
    parts=callback.data.split(":")
    action,uid=parts[2],int(parts[3])
    if action=="ban":
        row=await get_user(uid)
        is_banned=row[5]==1 if row and len(row)>5 else False
        await ban_user(uid, not is_banned)
        try: await callback.answer(f"{'بن شد' if not is_banned else 'آنبن شد'}")
        except: pass
        await cb_users(callback)
    elif action=="msg":
        await state.set_state(AdminState.wait_value)
        await state.update_data(cfg_key=f"dm_{uid}")
        await callback.message.answer(f"📨 پیام به <code>{uid}</code> (HTML):", parse_mode="HTML", reply_markup=cancel_kb())
        try: await callback.answer()
        except: pass

# ---------- Broadcast ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_broadcast)
    await callback.message.answer("📣 <b>همگانی</b>\nمتن/عکس/ویدیو بفرست — با تأیید به همه می‌ره!", parse_mode="HTML", reply_markup=cancel_kb())
    try: await callback.answer()
    except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_broadcast), F.text | F.photo | F.video | F.document)
async def msg_broadcast(message: Message, state: FSMContext, bot: Bot):
    kb=InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ تأیید و ارسال", callback_data="adm:bcast:confirm"), InlineKeyboardButton(text="❌ لغو", callback_data="adm:main"))
    await state.update_data(bcast_chat_id=message.chat.id, bcast_msg_id=message.message_id)
    await message.answer("⬆️ پیش‌نمایش — تأیید کن:", reply_markup=kb.as_markup())

@router.callback_query(ADMIN_FILTER, F.data == "adm:bcast:confirm")
async def cb_bcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data=await state.get_data()
    src_chat,src_msg=data.get("bcast_chat_id"),data.get("bcast_msg_id")
    if not src_chat or not src_msg:
        try: await callback.answer("اطلاعات نیست")
        except: pass
        return
    try: await callback.answer("شروع...")
    except: pass
    import aiosqlite
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned=0") as cur:
            rows=await cur.fetchall()
    total=len(rows)
    await callback.message.edit_text(f"📣 ارسال به {total} نفر... 0/{total}")
    sent=failed=0
    for (uid,) in rows:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
            sent+=1
        except: failed+=1
        if (sent+failed)%20==0: await asyncio.sleep(0.1)
        if (sent+failed)%100==0:
            try: await callback.message.edit_text(f"📣 {sent+failed}/{total} ✅{sent} ❌{failed}")
            except: pass
        await asyncio.sleep(0.05)
    await state.clear()
    await callback.message.edit_text(f"✅ تمام\n موفق: {sent}\n ناموفق: {failed}", reply_markup=back_to_main_kb())

# ---------- Logs ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:logs")
async def cb_logs(callback: CallbackQuery):
    import aiosqlite
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, platform, title, success, created_at FROM downloads_log ORDER BY id DESC LIMIT 15") as cur:
            rows=await cur.fetchall()
    if not rows:
        await callback.message.edit_text("📥 لاگی نیست.", reply_markup=back_to_main_kb())
        try: await callback.answer()
        except: pass
        return
    lines=["📥 <b>۱۵ دانلود اخیر:</b>\n"]
    for r in rows:
        uid,plat,title,ok,ts=r
        t=time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
        flag="✅" if ok else "❌"
        lines.append(f"{flag} {plat or '?'} | <code>{uid}</code> | {t}\n {escape_html((title or '')[:40])}")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_to_main_kb())
    try: await callback.answer()
    except: pass

# ---------- Cookies ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:cookies")
async def cb_cookies(callback: CallbackQuery):
    def exists(p: Path) -> str:
        return f"✅ {fmt_size(p.stat().st_size)}" if p.exists() and p.stat().st_size>10 else "❌ نیست"
    txt=(
        "🍪 <b>کوکی‌ها</b>\n"
        "Netscape cookies.txt via افزونه Get cookies.txt LOCALLY\n\n"
        f"• YouTube: {exists(COOKIES_YT)}\n"
        f"• Instagram: {exists(COOKIES_IG)}\n"
        f"• TikTok: {exists(COOKIES_TT)}\n"
        f"• Pinterest: {exists(COOKIES_PIN)}\n"
        f"• Twitter: {exists(COOKIES_TW)}\n"
        f"• Facebook: {exists(COOKIES_FB)}\n"
        f"• SoundCloud: {exists(COOKIES_SC)}\n"
        f"• Spotify: {exists(COOKIES_SP)}\n"
        f"• Threads: {exists(COOKIES_TH)}\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_cookies_kb())
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:cookies:"))
async def cb_cookies_sub(callback: CallbackQuery, state: FSMContext):
    sub=callback.data.split(":")[2]
    if sub=="help":
        await callback.message.answer("📖 افزونه <b>Get cookies.txt LOCALLY</b> نصب کن → خروجی رو اینجا به صورت فایل بفرست.", parse_mode="HTML", reply_markup=back_to_main_kb())
        try: await callback.answer()
        except: pass
        return
    elif sub=="clear":
        for p in (COOKIES_YT,COOKIES_IG,COOKIES_TT,COOKIES_PIN,COOKIES_TW,COOKIES_FB,COOKIES_SC,COOKIES_SP,COOKIES_TH, COOKIES_DIR/"cookies.txt"):
            try:
                if p.exists(): p.unlink()
            except: pass
        try: await callback.answer("حذف شد")
        except: pass
        await cb_cookies(callback)
        return
    elif sub=="up":
        plat=callback.data.split(":")[3]
        await state.set_state(AdminState.wait_cookie_upload)
        await state.update_data(cookie_platform=plat)
        await callback.message.answer(f"📤 فایل کوکی <b>{plat}</b> رو به صورت فایل بفرست.", parse_mode="HTML", reply_markup=cancel_kb())
        try: await callback.answer()
        except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_cookie_upload), F.document)
async def msg_cookie_upload(message: Message, state: FSMContext, bot: Bot):
    data=await state.get_data()
    plat=data.get("cookie_platform","youtube")
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    mapping={"youtube":COOKIES_YT,"instagram":COOKIES_IG,"tiktok":COOKIES_TT,"pinterest":COOKIES_PIN,"twitter":COOKIES_TW,"facebook":COOKIES_FB,"soundcloud":COOKIES_SC,"spotify":COOKIES_SP,"threads":COOKIES_TH}
    target=mapping.get(plat, COOKIES_DIR/"cookies.txt")
    try:
        file=await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, destination=target)
        h=target.read_text(errors="ignore")[:500]
        if "Netscape" not in h and len(h)<20:
            await message.answer("⚠️ فرمت مشکوکه ولی ذخیره شد.", reply_markup=back_to_main_kb())
        else:
            await message.answer(f"✅ کوکی <b>{plat}</b> ذخیره شد ({fmt_size(target.stat().st_size)})", parse_mode="HTML", reply_markup=back_to_main_kb())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ خطا: {e}", reply_markup=back_to_main_kb())
        await state.clear()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_cookie_upload), F.text)
async def msg_cookie_text(message: Message, state: FSMContext):
    if len(message.text or "")<30:
        await message.answer("❌ فایل رو به صورت Document بفرست.")
        return
    data=await state.get_data()
    plat=data.get("cookie_platform","youtube")
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    mapping={"youtube":COOKIES_YT,"instagram":COOKIES_IG,"tiktok":COOKIES_TT,"pinterest":COOKIES_PIN,"twitter":COOKIES_TW,"facebook":COOKIES_FB,"soundcloud":COOKIES_SC,"spotify":COOKIES_SP,"threads":COOKIES_TH}
    target=mapping.get(plat, COOKIES_DIR/"cookies.txt")
    target.write_text(message.text)
    await message.answer(f"✅ کوکی <b>{plat}</b> ذخیره شد.", parse_mode="HTML", reply_markup=back_to_main_kb())
    await state.clear()

# ---------- Captcha & Antispam ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:captcha")
async def cb_captcha_panel(callback: CallbackQuery):
    s=await get_all_settings()
    txt=(
        "🛡️ <b>کپچا و ضداسپم</b>\n\n"
        "کپچا فقط بار اول /start میاد — حالت فان: ایموجی 🍎\n"
        "ضداسپم: اگر کاربر بیش از حد لینک بفرسته موقت بن می‌شه.\n"
        f"کپچا: {'✅' if s.get('captcha_enabled')=='1' else '❌'} | حالت: {s.get('captcha_mode')}\n"
        f"ضداسپم: {'✅' if s.get('antispam_enabled')=='1' else '❌'} | فان: {'✅' if s.get('fun_mode')=='1' else '❌'}\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_captcha_kb(s))
    try: await callback.answer()
    except: pass

# ---------- Log channel ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:logchan")
async def cb_logchan(callback: CallbackQuery):
    s=await get_all_settings()
    ch=s.get("log_channel","") or "تنظیم نشده"
    txt=(
        "📢 <b>کانال لاگ</b>\n\n"
        "رویدادها (عضو جدید، دانلود، بن) کجا بره؟\n"
        f"کانال: <code>{escape_html(ch)}</code>\n"
        f"به ادمین خصوصی: {'✅' if s.get('log_to_admin_dm')=='1' else '❌'}\n"
        f"گزارش روزانه: {'✅' if s.get('daily_report_enabled')=='1' else '❌'} ساعت {s.get('daily_report_time','09:00')}\n"
        "ربات باید در کانال ادمین باشه.\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_logchan_kb(s))
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:logchan:set")
async def cb_logchan_set(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_log_channel)
    await callback.message.answer("📢 آیدی کانال لاگ رو بفرست (مثلاً @mylog یا -100123…):\nبرای حذف بنویس <code>clear</code>", parse_mode="HTML", reply_markup=cancel_kb())
    try: await callback.answer()
    except: pass

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_log_channel), F.text)
async def msg_logchan_set(message: Message, state: FSMContext):
    val=message.text.strip()
    if val.lower()=="clear": val=""
    await set_setting("log_channel", val)
    await state.clear()
    await message.answer(f"✅ کانال لاگ شد: <code>{escape_html(val or 'حذف شد')}</code>", parse_mode="HTML", reply_markup=back_to_main_kb())

@router.callback_query(ADMIN_FILTER, F.data == "adm:logchan:clear")
async def cb_logchan_clear(callback: CallbackQuery):
    await set_setting("log_channel","")
    try: await callback.answer("حذف شد")
    except: pass
    await cb_logchan(callback)

# ---------- Auto delete ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:autodel")
async def cb_autodel(callback: CallbackQuery):
    s=await get_all_settings()
    txt=(
        "🗑️ <b>حذف خودکار</b>\n\n"
        "ویدیو و صدا بعد از X ساعت خودکار پاک می‌شن (برای صرفه‌جویی).\n"
        f"فعلی: <b>{s.get('auto_delete_hours','0')} ساعت</b> (0=خاموش)\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_autodel_kb(s))
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:autodel:set:"))
async def cb_autodel_set(callback: CallbackQuery):
    hours=callback.data.split(":")[-1]
    await set_setting("auto_delete_hours", hours)
    try: await callback.answer(f"شد {hours} ساعت")
    except: pass
    await cb_autodel(callback)

# ---------- Fun mode ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:funmode")
async def cb_funmode(callback: CallbackQuery):
    cur=await get_setting("fun_mode","1")
    new="0" if cur=="1" else "1"
    await set_setting("fun_mode", new)
    try: await callback.answer(f"حالت فان {'روشن 😎' if new=='1' else 'خاموش'}")
    except: pass
    # Refresh main
    await show_main(callback)

# ---------- Status ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:status")
async def cb_status(callback: CallbackQuery):
    import psutil
    mem=psutil.virtual_memory()
    disk=shutil.disk_usage("/")
    svc="نامشخص"
    try:
        r=await asyncio.create_subprocess_exec("systemctl","is-active","mediodl-bot", stdout=asyncio.subprocess.PIPE)
        out,_=await r.communicate()
        svc=out.decode().strip() or "نامشخص"
    except: svc="نامشخص"
    # Count pending deletes
    import aiosqlite
    pending_del=0
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM auto_delete_queue") as cur:
                pending_del=(await cur.fetchone())[0]
    except: pass
    txt=(
        "🔄 <b>وضعیت سرویس</b>\n\n"
        f"• Service: <code>mediodl-bot</code> — <b>{svc}</b>\n"
        f"• RAM: {mem.percent}% ({fmt_size(mem.used)}/{fmt_size(mem.total)})\n"
        f"• Disk /: {fmt_size(disk.used)}/{fmt_size(disk.total)} آزاد {fmt_size(disk.free)}\n"
        f"• DB: {fmt_size(DATABASE_PATH.stat().st_size) if DATABASE_PATH.exists() else '—'}\n"
        f"• TMP: {fmt_size(sum(f.stat().st_size for f in TMP_DIR.glob('**/*') if f.is_file())) if TMP_DIR.exists() else '—'}\n"
        f"• حذف صف: {pending_del} پیام\n"
        f"• کوکی‌ها: YT {'✅' if COOKIES_YT.exists() else '❌'} | IG {'✅' if COOKIES_IG.exists() else '❌'} | TT {'✅' if COOKIES_TT.exists() else '❌'}\n"
        f"• پین {'✅' if COOKIES_PIN.exists() else '❌'} توییتر {'✅' if COOKIES_TW.exists() else '❌'} فیسبوک {'✅' if COOKIES_FB.exists() else '❌'}\n\n"
        "<code>mediodl status</code>\n<code>mediodl logs -f</code>\n"
    )
    kb=InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🧹 پاکسازی tmp", callback_data="adm:cleanup"), InlineKeyboardButton(text="🔄 ریستارت", callback_data="adm:restart"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=kb.as_markup())
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:cleanup")
async def cb_cleanup(callback: CallbackQuery):
    cleaned=0; size_before=0
    if TMP_DIR.exists():
        for p in TMP_DIR.glob("dl_*"):
            try: size_before+=sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            except: pass
        now=time.time()
        for p in TMP_DIR.glob("dl_*"):
            try:
                if now-p.stat().st_mtime>600:
                    shutil.rmtree(p, ignore_errors=True); cleaned+=1
            except: pass
    try: await callback.answer(f"پاک شد: {cleaned} ({fmt_size(size_before)})")
    except: pass
    await cb_status(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:restart")
async def cb_restart(callback: CallbackQuery):
    try:
        proc=await asyncio.create_subprocess_exec("systemctl","restart","mediodl-bot", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        if proc.returncode==0: 
            try: await callback.answer("ریستارت شد ✅", show_alert=True)
            except: pass
        else:
            try: await callback.answer("خطا — لاگ رو چک کن", show_alert=True)
            except: pass
    except Exception as e:
        try: await callback.answer(f"ناموفق: {e}", show_alert=True)
        except: pass

# ---------- Update ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:update")
async def cb_update(callback: CallbackQuery):
    txt=(
        "🔄 <b>بروزرسانی ربات</b>\n\n"
        "برای آپدیت به آخرین نسخه از گیتهاب:\n"
        "<code>mediodl update</code>\n\n"
        "یا دستی:\n"
        "<code>cd /opt/mediodl-bot && git pull && ./venv/bin/pip install -r requirements.txt && systemctl restart mediodl-bot</code>\n\n"
        "می‌خوای همین الان از طریق ربات آپدیت کنم؟"
    )
    kb=InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ بله، آپدیت کن", callback_data="adm:update:do"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=kb.as_markup())
    try: await callback.answer()
    except: pass

@router.callback_query(ADMIN_FILTER, F.data == "adm:update:do")
async def cb_update_do(callback: CallbackQuery):
    await callback.message.edit_text("⏳ در حال بروزرسانی... چند ثانیه صبر کن (ربات ریستارت می‌شه)", parse_mode="HTML")
    try: await callback.answer()
    except: pass
    # Run in background so we can respond before restart kills us
    async def _do():
        await asyncio.sleep(1)
        try:
            proc=await asyncio.create_subprocess_exec("bash","-c","cd /opt/mediodl-bot && git pull --rebase --autostash && ./venv/bin/pip install -q -r requirements.txt && systemctl restart mediodl-bot", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
        except: pass
    asyncio.create_task(_do())
