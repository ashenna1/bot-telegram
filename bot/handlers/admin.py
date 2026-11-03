"""
Admin panel - comprehensive professional UI inside Telegram
"""
import time
import asyncio
import os
import re
import shutil
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import ADMIN_IDS, is_admin, DATABASE_PATH, TMP_DIR, COOKIES_DIR, COOKIES_YT, COOKIES_IG, COOKIES_TT, VERSION
from bot.db import (
    get_all_settings, get_setting, set_setting,
    add_channel, remove_channel, toggle_channel, list_channels,
    add_ad, list_ads, toggle_ad, remove_ad,
    count_users, list_users, ban_user, get_user,
    get_stats,
)
from bot.keyboards.inline import (
    admin_main_kb, admin_settings_kb, admin_channels_kb, admin_ads_kb,
    admin_users_kb, admin_cookies_kb, back_to_main_kb, cancel_kb
)
from bot.utils.helpers import fmt_size, fmt_duration, escape_html, truncate

log = logging.getLogger("admin")
router = Router()

# Only admins can access this router — applied per-handler below
ADMIN_FILTER = F.from_user.id.in_(ADMIN_IDS)

# --- FSM ---
class AdminState(StatesGroup):
    wait_value = State()       # generic text input
    wait_channel = State()     # add channel
    wait_ad_text = State()     # ad steps
    wait_ad_button = State()
    wait_broadcast = State()
    wait_user_search = State()
    wait_cookie_upload = State()

_pending = {}  # user_id -> context dict for multi-step

def _is_admin(uid: int) -> bool:
    return is_admin(uid)

# --- Guard for non-admin ---
@router.message(ADMIN_FILTER, Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await show_main(message)

async def show_main(target: Message | CallbackQuery):
    settings = await get_all_settings()
    total_users = await count_users()
    stats = await get_stats(days=1)
    today = stats[0] if stats else ("—", 0, 0, 0)
    txt = (
        "👑 <b>پنل مدیریت MediODL</b>\n"
        f"🏷️ نسخه: <code>{VERSION}</code>\n"
        f"👥 کل کاربران: <b>{total_users}</b>\n"
        f"📥 دانلود امروز: <b>{today[1] if len(today)>1 else 0}</b> | درخواست امروز: <b>{today[3] if len(today)>3 else 0}</b>\n"
        f"⚙️ کیفیت: <b>{settings.get('max_video_height','1080')}p</b> | تعمیر: <b>{'ON' if settings.get('maintenance_mode')=='1' else 'OFF'}</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "یک گزینه را انتخاب کن:"
    )
    kb = admin_main_kb()
    if isinstance(target, Message):
        await target.answer(txt, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await target.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await target.message.answer(txt, parse_mode="HTML", reply_markup=kb)
        await target.answer()

@router.callback_query(ADMIN_FILTER, F.data == "adm:main")
async def cb_main(callback: CallbackQuery):
    await show_main(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:close")
async def cb_close(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("بسته شد.")

# ---------- Stats ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery):
    total = await count_users()
    banned = await count_users("WHERE is_banned=1")
    stats7 = await get_stats(days=7)
    # DB size
    db_size = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
    tmp_size = sum(f.stat().st_size for f in TMP_DIR.glob("**/*") if f.is_file()) if TMP_DIR.exists() else 0

    lines = [
        "📊 <b>آمار ربات</b>\n",
        f"👥 کل کاربران: <b>{total}</b> | 🚫 مسدود: <b>{banned}</b>",
        f"💾 حجم دیتابیس: <b>{fmt_size(db_size)}</b> | 📦 tmp: <b>{fmt_size(tmp_size)}</b>",
        "",
        "📅 <b>7 روز اخیر:</b>",
        "<code>تاریخ        | دانلود | اعضا+ | درخواست</code>",
    ]
    for row in stats7:
        lines.append(f"<code>{row[0]} | {row[1]:>6} | {row[2]:>6} | {row[3]:>7}</code>")
    if not stats7:
        lines.append("هنوز آماری ثبت نشده.")
    lines += ["", "💡 برای جزئیات بیشتر: <code>mediodl status</code> در سرور"]
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_to_main_kb())
    await callback.answer()

# ---------- Settings ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery):
    s = await get_all_settings()
    txt = (
        "⚙️ <b>تنظیمات ربات</b>\n\n"
        "هر مورد را لمس کن تا مقدارش را تغییر دهی:\n"
        f"• کیفیت ویدیو بر حسب p (مثلاً 1080)\n"
        f"• کپشن و پیام خوش‌آمد (قالب با متغیرهای {title} و ...)\n"
        f"• حالت تعمیر و محدودیت‌ها\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_settings_kb(s))
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:cfg:"))
async def cb_cfg(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 2)[2]
    s = await get_all_settings()
    cur = s.get(key, "")

    # Toggles
    if key in ("show_audio_separately", "maintenance_mode"):
        new = "0" if cur == "1" else "1"
        await set_setting(key, new)
        await callback.answer(f"{key} → {new}")
        # refresh
        ns = await get_all_settings()
        try:
            await callback.message.edit_reply_markup(reply_markup=admin_settings_kb(ns))
        except Exception:
            pass
        return

    # Value inputs
    prompts = {
        "max_video_height": "🎞️ حداکثر کیفیت ویدیو را بفرست (عدد، مثلاً 1080، 720، 480):\nفعلی: <code>{cur}</code>",
        "caption_template": "📝 قالب کپشن ویدیو را بفرست:\nمتغیرها: <code>{title}</code> <code>{uploader}</code> <code>{view_count}</code> <code>{like_count}</code> <code>{duration}</code> <code>{bot_username}</code>\n\nفعلی:\n<code>{cur}</code>",
        "welcome_message": "👋 پیام خوش‌آمد را بفرست (از {name} برای نام کاربر استفاده کن):\n\nفعلی:\n{cur}",
        "max_duration_sec": "⏱️ حداکثر طول ویدیو به ثانیه (مثلاً 3600 = یک ساعت):\nفعلی: <code>{cur}</code>",
        "rate_limit_per_hour": "🚦 سقف درخواست هر کاربر در ساعت (عدد):\nفعلی: <code>{cur}</code>",
        "maintenance_text": "🛠️ متن حالت تعمیر را بفرست:\nفعلی:\n{cur}",
    }
    prompt = prompts.get(key, f"مقدار جدید برای <code>{key}</code> را بفرست:\nفعلی: <code>{cur}</code>")
    prompt = prompt.format(cur=escape_html(cur[:800] if key != "welcome_message" else cur[:800]))
    await state.set_state(AdminState.wait_value)
    await state.update_data(cfg_key=key)
    await callback.message.answer(prompt, parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_value), F.text)
async def msg_cfg_value(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    key = data.get("cfg_key")
    val = message.text.strip()

    # --- Ad every pending (3rd step of ad creation) ---
    if key == "ad_every_pending":
        try:
            every = int(val)
        except Exception:
            every = 3
        every = max(1, min(every, 100))
        await add_ad(data.get("ad_text",""), data.get("ad_photo"), data.get("ad_btn_text"), data.get("ad_btn_url"), show_every=every)
        await state.clear()
        await message.answer(f"✅ تبلیغ اضافه شد (هر {every} دانلود).", reply_markup=back_to_main_kb())
        return

    # --- Direct message to user (dm_xxx) ---
    if key and key.startswith("dm_"):
        target_id = int(key.split("_", 1)[1])
        try:
            await bot.send_message(chat_id=target_id, text=val, parse_mode="HTML")
            await message.answer(f"✅ پیام به <code>{target_id}</code> ارسال شد.", parse_mode="HTML", reply_markup=back_to_main_kb())
        except Exception as e:
            await message.answer(f"❌ ارسال ناموفق: {e}", reply_markup=back_to_main_kb())
        await state.clear()
        return

    # --- Normal setting update ---
    if not key:
        await state.clear()
        await message.answer("❌ وضعیت نامشخص. /admin را دوباره بزن.", reply_markup=back_to_main_kb())
        return
    if key in ("max_video_height", "max_duration_sec", "rate_limit_per_hour"):
        if not val.isdigit():
            await message.answer("❌ فقط عدد بفرست. دوباره تلاش کن:")
            return
    await set_setting(key, val)
    await state.clear()
    await message.answer(f"✅ <b>{key}</b> به‌روزرسانی شد:\n<code>{escape_html(val[:500])}</code>", parse_mode="HTML", reply_markup=back_to_main_kb())

# ---------- Channels ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:channels")
async def cb_channels(callback: CallbackQuery):
    chs = await list_channels()
    txt = (
        "📢 <b>کانال‌های عضویت اجباری</b>\n\n"
        "کاربر تا عضو همه کانال‌های فعال نشود، نمی‌تواند دانلود کند.\n"
        "• @username یا لینک t.me را وارد کن\n"
        "• برای کانال خصوصی، لینک دعوت (invite) را بگذار\n"
        "• ربات باید در کانال ادمین باشد تا عضویت چک شود (وگرنه هشدار می‌دهد)\n\n"
        f"وضعیت فعلی: <b>{'فعال ✅' if await get_setting('force_join_enabled','0')=='1' else 'غیرفعال ⏸️'}</b> — برای تغییر: /admin → تنظیمات → force_join_enabled\n"
        f"تعداد: {len(chs)}\n"
    )
    # Build toggle-all button inline manually
    kb = admin_channels_kb(chs)
    # Add enable/disable toggle on top
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    enabled = await get_setting("force_join_enabled", "0") == "1"
    toggle_btn = InlineKeyboardButton(text=f"{'⏸️ غیرفعال‌سازی عضویت اجباری' if enabled else '✅ فعال‌سازی عضویت اجباری'}", callback_data="adm:ch:toggle_force")
    # Inject
    new_kb = kb.inline_keyboard
    new_kb.insert(0, [toggle_btn])
    kb2 = InlineKeyboardMarkup(inline_keyboard=new_kb)
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=kb2)
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:toggle_force")
async def cb_toggle_force(callback: CallbackQuery):
    cur = await get_setting("force_join_enabled", "0")
    new = "0" if cur == "1" else "1"
    await set_setting("force_join_enabled", new)
    await callback.answer(f"عضویت اجباری {'فعال' if new=='1' else 'غیرفعال'} شد")
    await cb_channels(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:add")
async def cb_ch_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_channel)
    await callback.message.answer(
        "➕ <b>افزودن کانال</b>\n\n"
        "فرمت‌ها (هر خط یک کانال):\n"
        "<code>@my_channel</code>\n"
        "<code>https://t.me/my_channel</code>\n"
        "<code>@my_channel | https://t.me/+inviteHash</code> (برای کانال خصوصی، بخش دوم لینک دعوت است)\n\n"
        "لینک را بفرست:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_channel), F.text)
async def msg_ch_add(message: Message, state: FSMContext):
    lines = [l.strip() for l in message.text.splitlines() if l.strip()]
    added = 0
    for line in lines:
        invite = ""
        title = ""
        if "|" in line:
            part1, part2 = line.split("|", 1)
            username = part1.strip()
            invite = part2.strip()
        else:
            username = line.strip()
        # Normalize
        if not username:
            continue
        await add_channel(username, invite_link=invite, title=title)
        added += 1
    await state.clear()
    await message.answer(f"✅ {added} کانال اضافه شد.", reply_markup=back_to_main_kb())
    # Verify bot can check membership
    if added:
        await message.answer("💡 یادآوری: ربات را در کانال(ها) ادمین کن تا بررسی عضویت دقیق کار کند.", reply_markup=back_to_main_kb())

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:ch:"))
async def cb_ch_action(callback: CallbackQuery):
    parts = callback.data.split(":")
    # adm:ch:toggle:3  adm:ch:del:3  adm:ch:noop:3
    if len(parts) < 4:
        await callback.answer()
        return
    action, cid = parts[2], parts[3]
    if action == "noop":
        await callback.answer(f"کانال #{cid}")
        return
    if action == "toggle":
        await toggle_channel(int(cid))
        await callback.answer("تغییر وضعیت ✅")
    elif action == "del":
        await remove_channel(int(cid))
        await callback.answer("حذف شد 🗑️")
    elif action == "help":
        await callback.answer()
        return
    # refresh
    await cb_channels(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:ch:help")
async def cb_ch_help(callback: CallbackQuery):
    await callback.message.answer(
        "💡 <b>راهنمای عضویت اجباری</b>\n\n"
        "1) ربات را در کانال ادمین کن (حداقل دسترسی خواندن اعضا).\n"
        "2) یوزرنیم کانال (@username) را در پنل اضافه کن.\n"
        "3) «بررسی عضویت» را خودت تست کن با یک اکانت دوم.\n"
        "4) اگر ربات ادمین نیست، بررسی عضویت کار نمی‌کند و ربات به کاربر اجازه عبور می‌دهد (برای جلوگیری از قفل شدن).\n"
        "5) برای کانال خصوصی از لینک دعوت استفاده کن.",
        parse_mode="HTML",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()

# ---------- Ads ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:ads")
async def cb_ads(callback: CallbackQuery):
    ads = await list_ads()
    txt = (
        "📣 <b>مدیریت تبلیغات</b>\n\n"
        "هر تبلیغ می‌تواند متن + عکس + دکمه داشته باشد.\n"
        "• <b>show_every</b>: هر چند دانلود یک‌بار نمایش داده شود (پیش‌فرض 3)\n"
        "• اگر چند تبلیغ فعال باشد، به نوبت نمایش داده می‌شوند\n"
        f"تعداد: {len(ads)}\n"
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_ads_kb(ads))
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data == "adm:ad:add")
async def cb_ad_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_ad_text)
    await callback.message.answer(
        "➕ <b>افزودن تبلیغ — مرحله 1/3</b>\n\n"
        "متن تبلیغ را بفرست (HTML پشتیبانی می‌شود، مثلاً &lt;b&gt;bold&lt;/b&gt;):\n"
        "اگر می‌خواهی تبلیغ با عکس باشد، همین حالا عکس را با کپشن (متن تبلیغ) بفرست.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_ad_text), F.text | F.photo)
async def msg_ad_text(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    await state.update_data(ad_text=text[:3000], ad_photo=photo_id)
    await state.set_state(AdminState.wait_ad_button)
    await message.answer(
        "➕ <b>مرحله 2/3 — دکمه (اختیاری)</b>\n\n"
        "اگر می‌خواهی دکمه داشته باشد، به این فرمت بفرست:\n"
        "<code>متن دکمه | https://example.com</code>\n"
        "برای بدون دکمه، بنویس: <code>skip</code> یا <code>رد</code>",
        parse_mode="HTML",
    )

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_ad_button), F.text)
async def msg_ad_button(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data.get("ad_text", "")
    photo_id = data.get("ad_photo")
    raw = message.text.strip()
    btn_text, btn_url = None, None
    if raw.lower() not in ("skip", "رد", "-", "بدون"):
        if "|" in raw:
            a, b = raw.split("|", 1)
            btn_text = a.strip()[:30]
            btn_url = b.strip()
        else:
            btn_text = raw[:30]
            btn_url = None
    # show_every
    await state.update_data(ad_btn_text=btn_text, ad_btn_url=btn_url)
    # ask show_every
    await message.answer(
        "➕ <b>مرحله 3/3 — تناوب نمایش</b>\n\n"
        "هر چند دانلود یک‌بار این تبلیغ نمایش داده شود؟\n"
        "عدد بفرست (مثلاً 3 یعنی هر 3 دانلود). پیش‌فرض: 3",
        parse_mode="HTML",
    )
    # Next message handles show_every via same state but we switch logic
    # Use simple flag
    await state.set_state(AdminState.wait_value)
    await state.update_data(cfg_key="ad_every_pending", ad_text=text, ad_photo=photo_id, ad_btn_text=btn_text, ad_btn_url=btn_url)

# (ادغام شد در msg_cfg_value — نگهداری برای سازگاری حذف شد)

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:ad:"))
async def cb_ad_action(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    action, aid = parts[2], parts[3]
    if action == "noop":
        await callback.answer(f"تبلیغ #{aid}")
        return
    if action == "toggle":
        await toggle_ad(int(aid))
        await callback.answer("تغییر وضعیت ✅")
    elif action == "del":
        await remove_ad(int(aid))
        await callback.answer("حذف شد 🗑️")
    await cb_ads(callback)

# ---------- Users ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:users")
async def cb_users(callback: CallbackQuery):
    await callback.message.edit_text(
        "👥 <b>مدیریت کاربران</b>\n\n"
        "• لیست 20 کاربر اخیر\n"
        "• جستجو بر اساس آیدی یا یوزرنیم\n"
        "• بن / آنبن کردن\n",
        parse_mode="HTML",
        reply_markup=admin_users_kb(),
    )
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:users:"))
async def cb_users_sub(callback: CallbackQuery, state: FSMContext):
    sub = callback.data.split(":")[2]
    if sub == "list":
        offset = int(callback.data.split(":")[3]) if len(callback.data.split(":")) > 3 else 0
        rows = await list_users(limit=20, offset=offset)
        if not rows:
            await callback.answer("کاربری یافت نشد.")
            return
        lines = ["👥 <b>کاربران اخیر:</b>\n"]
        kb = InlineKeyboardBuilder()
        for r in rows:
            uid, uname, fname, dls, banned = r
            flag = "🚫" if banned else "✅"
            lines.append(f"{flag} <code>{uid}</code> @{uname or '-'} — {escape_html(fname or '')} | 📥{dls}")
            kb.row(
                InlineKeyboardButton(text=f"{'آنبن' if banned else 'بن'} {uid}", callback_data=f"adm:usr:ban:{uid}"),
                InlineKeyboardButton(text=f"📨 پیام به {uid}", callback_data=f"adm:usr:msg:{uid}"),
            )
        # pagination
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"adm:users:list:{max(0, offset-20)}"))
        if len(rows) == 20:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"adm:users:list:{offset+20}"))
        if nav:
            kb.row(*nav)
        kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:users"))
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()
    elif sub == "search":
        await state.set_state(AdminState.wait_user_search)
        await callback.message.answer("🔍 آیدی عددی یا @یوزرنیم کاربر را بفرست:", reply_markup=cancel_kb())
        await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_user_search), F.text)
async def msg_user_search(message: Message, state: FSMContext):
    q = message.text.strip().lstrip("@")
    # try user_id
    if q.isdigit():
        row = await get_user(int(q))
        rows = [row] if row else []
    else:
        # search by username
        import aiosqlite
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT user_id, username, fullname, downloads, is_banned FROM users WHERE username LIKE ? LIMIT 10", (f"%{q}%",)) as cur:
                rows = await cur.fetchall()
                # adapt to same shape but with extra cols
                if rows:
                    # fetch full rows for display
                    pass
    await state.clear()
    if not rows or not rows[0]:
        await message.answer("❌ کاربری یافت نشد.", reply_markup=back_to_main_kb())
        return
    # rows from get_user is full tuple; from search is limited
    lines = []
    kb = InlineKeyboardBuilder()
    for r in rows:
        if r is None:
            continue
        # normalize
        if len(r) >= 5:
            # search result: user_id, username, fullname, downloads, is_banned
            uid, uname, fname, dls, banned = r[0], r[1], r[2], r[3], r[4]
        else:
            uid, uname, fname = r[0], r[1], r[2]
            dls, banned = r[7] if len(r) > 7 else 0, r[5] if len(r) > 5 else 0
        flag = "🚫" if banned else "✅"
        lines.append(f"{flag} <code>{uid}</code> @{uname or '-'} — {escape_html(fname or '')} | 📥{dls}")
        kb.row(
            InlineKeyboardButton(text=f"{'آنبن' if banned else 'بن'} {uid}", callback_data=f"adm:usr:ban:{uid}"),
            InlineKeyboardButton(text=f"📨 پیام", callback_data=f"adm:usr:msg:{uid}"),
        )
    kb.row(InlineKeyboardButton(text="🔙 پنل", callback_data="adm:main"))
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:usr:"))
async def cb_usr_action(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action, uid = parts[2], int(parts[3])
    if action == "ban":
        row = await get_user(uid)
        is_banned = row[5] == 1 if row and len(row) > 5 else False
        await ban_user(uid, ban=not is_banned)
        await callback.answer(f"{'بن شد 🚫' if not is_banned else 'آنبن شد ✅'}")
        # refresh list first page
        await cb_users(callback)
    elif action == "msg":
        await state.set_state(AdminState.wait_value)
        await state.update_data(cfg_key=f"dm_{uid}")
        await callback.message.answer(f"📨 پیام مستقیم به <code>{uid}</code> را بفرست (HTML مجاز):", parse_mode="HTML", reply_markup=cancel_kb())
        await callback.answer()

# ---------- DM handling is unified in msg_cfg_value above ----------

# ---------- Broadcast ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_broadcast)
    await callback.message.answer(
        "📣 <b>پیام همگانی</b>\n\n"
        "متنی که می‌خواهی به همه کاربران ارسال شود را بفرست (HTML مجاز).\n"
        "می‌توانی عکس با کپشن هم بفرستی.\n\n"
        "⚠️ با دقت — این پیام به همه ارسال می‌شود!",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_broadcast), F.text | F.photo | F.video | F.document)
async def msg_broadcast(message: Message, state: FSMContext, bot: Bot):
    # confirm
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ تأیید و ارسال به همه", callback_data="adm:bcast:confirm"),
        InlineKeyboardButton(text="❌ لغو", callback_data="adm:main"),
    )
    # store message id to copy
    await state.update_data(bcast_chat_id=message.chat.id, bcast_msg_id=message.message_id)
    await message.answer("⬆️ این پیام پیش‌نمایش بود. برای ارسال همگانی تأیید کن:", reply_markup=kb.as_markup())

@router.callback_query(ADMIN_FILTER, F.data == "adm:bcast:confirm")
async def cb_bcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    src_chat = data.get("bcast_chat_id")
    src_msg = data.get("bcast_msg_id")
    if not src_chat or not src_msg:
        await callback.answer("اطلاعات پیام یافت نشد.")
        return
    await callback.answer("شروع ارسال...")
    # fetch all user_ids
    import aiosqlite
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned=0") as cur:
            rows = await cur.fetchall()
    total = len(rows)
    await callback.message.edit_text(f"📣 در حال ارسال به {total} کاربر... (0/{total})", parse_mode="HTML")
    sent = 0
    failed = 0
    for (uid,) in rows:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 20 == 0:
            # small delay to avoid flood, update progress sometimes
            await asyncio.sleep(0.1)
            try:
                if (sent + failed) % 100 == 0:
                    await callback.message.edit_text(f"📣 در حال ارسال... ({sent+failed}/{total}) — ✅{sent} ❌{failed}")
            except Exception:
                pass
        # Telegram per-second limit ~30 msg/s; pace 0.05s
        await asyncio.sleep(0.05)
    await state.clear()
    await callback.message.edit_text(f"✅ پایان ارسال همگانی\n📤 موفق: {sent}\n❌ ناموفق: {failed}\n👥 کل: {total}", reply_markup=back_to_main_kb())

# ---------- Logs ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:logs")
async def cb_logs(callback: CallbackQuery):
    import aiosqlite
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, platform, title, success, created_at FROM downloads_log ORDER BY id DESC LIMIT 15") as cur:
            rows = await cur.fetchall()
    if not rows:
        await callback.message.edit_text("📥 هنوز لاگی ثبت نشده.", reply_markup=back_to_main_kb())
        await callback.answer()
        return
    lines = ["📥 <b>15 دانلود اخیر:</b>\n"]
    for r in rows:
        uid, plat, title, ok, ts = r
        t = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
        flag = "✅" if ok else "❌"
        lines.append(f"{flag} {plat or '?'} | <code>{uid}</code> | {t}\n {escape_html((title or '')[:40])}")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_to_main_kb())
    await callback.answer()

# ---------- Cookies ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:cookies")
async def cb_cookies(callback: CallbackQuery):
    def exists(p: Path) -> str:
        if p.exists() and p.stat().st_size > 10:
            return f"✅ {fmt_size(p.stat().st_size)}"
        return "❌ موجود نیست"
    txt = (
        "🍪 <b>مدیریت کوکی‌ها</b>\n\n"
        "برای دانلود محتوای خصوصی/محدود، کوکی مرورگر را آپلود کن.\n"
        "فرمت: Netscape cookies.txt\n"
        "نحوه خروجی: افزونه Get cookies.txt LOCALLY در مرورگر\n\n"
        f"• YouTube: <code>cookies/youtube.txt</code> — {exists(COOKIES_YT)}\n"
        f"• Instagram: <code>cookies/instagram.txt</code> — {exists(COOKIES_IG)}\n"
        f"• TikTok: <code>cookies/tiktok.txt</code> — {exists(COOKIES_TT)}\n\n"
        "هر فایل را جداگانه آپلود کن. بعد از آپلود، ربات خودکار از آن استفاده می‌کند."
    )
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_cookies_kb())
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data.startswith("adm:cookies:"))
async def cb_cookies_sub(callback: CallbackQuery, state: FSMContext):
    sub = callback.data.split(":")[2]
    if sub == "help":
        await callback.message.answer(
            "📖 <b>راهنمای کوکی</b>\n\n"
            "1) در مرورگر وارد YouTube/Instagram/TikTok شو (با اکانتی که به محتوا دسترسی دارد).\n"
            "2) افزونه <b>Get cookies.txt LOCALLY</b> را نصب کن (کروم/فایرفاکس).\n"
            "3) خروجی را به صورت cookies.txt ذخیره کن.\n"
            "4) فایل را اینجا آپلود کن (Send as file).\n"
            "5) ربات خودکار از آن برای دور زدن محدودیت‌ها استفاده می‌کند.\n\n"
            "⚠️ کوکی‌ها را با کسی به اشتراک نگذار!",
            parse_mode="HTML",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    elif sub == "clear":
        for p in (COOKIES_YT, COOKIES_IG, COOKIES_TT, COOKIES_DIR / "cookies.txt"):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        await callback.answer("حذف شد 🗑️")
        await cb_cookies(callback)
        return
    elif sub == "up":
        plat = callback.data.split(":")[3]  # youtube/instagram/tiktok
        await state.set_state(AdminState.wait_cookie_upload)
        await state.update_data(cookie_platform=plat)
        await callback.message.answer(
            f"📤 فایل کوکی <b>{plat}</b> را به صورت <b>File/Document</b> بفرست (نه متن کپی شده).\n"
            f"فرمت Netscape و شامل header <code># Netscape HTTP Cookie File</code> باشد.\n"
            f"برای لغو: /admin",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        await callback.answer()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_cookie_upload), F.document)
async def msg_cookie_upload(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    plat = data.get("cookie_platform", "youtube")
    doc = message.document
    # download file
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    target = {"youtube": COOKIES_YT, "instagram": COOKIES_IG, "tiktok": COOKIES_TT}.get(plat, COOKIES_DIR / "cookies.txt")
    dest = target
    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, destination=dest)
        if dest.stat().st_size < 10:
            raise ValueError("فایل خالی است")
        # validate header
        head = dest.read_text(errors="ignore")[:500]
        if "Netscape" not in head and "Cookie" not in head and len(head) < 20:
            await message.answer("⚠️ هشدار: فایل شبیه cookies.txt به نظر نمی‌رسد، ولی ذخیره شد. اگر کار نکرد، فرمت Netscape را چک کن.", reply_markup=back_to_main_kb())
        else:
            await message.answer(f"✅ کوکی <b>{plat}</b> ذخیره شد ({fmt_size(dest.stat().st_size)})", parse_mode="HTML", reply_markup=back_to_main_kb())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ خطا در ذخیره کوکی: {e}", reply_markup=back_to_main_kb())
        await state.clear()

@router.message(ADMIN_FILTER, StateFilter(AdminState.wait_cookie_upload), F.text)
async def msg_cookie_text_fallback(message: Message, state: FSMContext):
    # allow pasting raw cookie text too
    text = message.text or ""
    if len(text) < 30:
        await message.answer("❌ فایل را به صورت Document بفرست، نه متن کوتاه.")
        return
    data = await state.get_data()
    plat = data.get("cookie_platform", "youtube")
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    target = {"youtube": COOKIES_YT, "instagram": COOKIES_IG, "tiktok": COOKIES_TT}.get(plat, COOKIES_DIR / "cookies.txt")
    target.write_text(text)
    await message.answer(f"✅ کوکی <b>{plat}</b> از روی متن ذخیره شد.", parse_mode="HTML", reply_markup=back_to_main_kb())
    await state.clear()

# ---------- Status / Service ----------
@router.callback_query(ADMIN_FILTER, F.data == "adm:status")
async def cb_status(callback: CallbackQuery):
    # Gather diagnostic info
    import psutil
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    # Service status via systemctl if available
    svc = "نامشخص"
    try:
        r = await asyncio.create_subprocess_exec("systemctl", "is-active", "mediodl-bot", stdout=asyncio.subprocess.PIPE)
        out, _ = await r.communicate()
        svc = out.decode().strip() or "نامشخص"
    except Exception:
        svc = "نامشخص (systemd در دسترس نیست)"
    txt = (
        "🔄 <b>وضعیت سرویس</b>\n\n"
        f"• Service: <code>mediodl-bot.service</code> — <b>{svc}</b>\n"
        f"• RAM: {mem.percent}% ({fmt_size(mem.used)} / {fmt_size(mem.total)})\n"
        f"• Disk /: {fmt_size(disk.used)} / {fmt_size(disk.total)} آزاد {fmt_size(disk.free)}\n"
        f"• DB: <code>{DATABASE_PATH}</code> — {fmt_size(DATABASE_PATH.stat().st_size) if DATABASE_PATH.exists() else '—'}\n"
        f"• TMP: <code>{TMP_DIR}</code> — {fmt_size(sum(f.stat().st_size for f in TMP_DIR.glob('**/*') if f.is_file())) if TMP_DIR.exists() else '—'}\n"
        f"• کوکی‌ها: یوتیوب {'✅' if COOKIES_YT.exists() else '❌'} | اینستا {'✅' if COOKIES_IG.exists() else '❌'} | تیک‌تاک {'✅' if COOKIES_TT.exists() else '❌'}\n\n"
        "دستورات سرور:\n"
        "<code>mediodl status</code>\n"
        "<code>mediodl logs -f</code>\n"
        "<code>mediodl restart</code>\n"
        "<code>systemctl status mediodl-bot</code>\n"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🧹 پاکسازی tmp", callback_data="adm:cleanup"),
        InlineKeyboardButton(text="🔄 ریستارت", callback_data="adm:restart"),
    )
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    await callback.message.edit_text(txt, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()

@router.callback_query(ADMIN_FILTER, F.data == "adm:cleanup")
async def cb_cleanup(callback: CallbackQuery):
    cleaned = 0
    size_before = 0
    if TMP_DIR.exists():
        for p in TMP_DIR.glob("dl_*"):
            try:
                sz = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                size_before += sz
            except Exception:
                pass
        # clean old >10 min
        now = time.time()
        for p in TMP_DIR.glob("dl_*"):
            try:
                if now - p.stat().st_mtime > 600:
                    shutil.rmtree(p, ignore_errors=True)
                    cleaned += 1
            except Exception:
                pass
    await callback.answer(f"پاک شد: {cleaned} پوشه ({fmt_size(size_before)})")
    await cb_status(callback)

@router.callback_query(ADMIN_FILTER, F.data == "adm:restart")
async def cb_restart(callback: CallbackQuery):
    try:
        proc = await asyncio.create_subprocess_exec("systemctl", "restart", "mediodl-bot", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        if proc.returncode == 0:
            await callback.answer("ریستارت شد ✅", show_alert=True)
        else:
            await callback.answer("خطا در ریستارت — لاگ را چک کن", show_alert=True)
    except Exception as e:
        await callback.answer(f"ناموفق: {e}", show_alert=True)

# ---------- Fallback: handle direct Document broadcast already covered; channel add etc. ----------