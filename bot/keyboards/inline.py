"""
Inline keyboards
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.utils.force_join import channel_button_url

# ---------- User ----------
def force_join_kb(missing: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in missing:
        _, username, title, invite_link, _ = ch
        url = channel_button_url(ch)
        label = title or username or url
        kb.row(InlineKeyboardButton(text=f"🔗 عضویت: {label[:30]}", url=url))
    kb.row(InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="check_join"))
    return kb.as_markup()

def after_video_kb(platform: str, url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎬 دانلود دوباره", callback_data=f"redl:{platform}"),
        InlineKeyboardButton(text="🔗 لینک اصلی", url=url[:200]),
    )
    kb.row(InlineKeyboardButton(text="📤 اشتراک‌گذاری", switch_inline_query=url[:100]))
    return kb.as_markup()

# ---------- Admin ----------
def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 آمار", callback_data="adm:stats"),
        InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings"),
    )
    kb.row(
        InlineKeyboardButton(text="📢 کانال‌های اجباری", callback_data="adm:channels"),
        InlineKeyboardButton(text="📣 تبلیغات", callback_data="adm:ads"),
    )
    kb.row(
        InlineKeyboardButton(text="👥 کاربران", callback_data="adm:users"),
        InlineKeyboardButton(text="📥 لاگ دانلودها", callback_data="adm:logs"),
    )
    kb.row(
        InlineKeyboardButton(text="🍪 کوکی‌ها", callback_data="adm:cookies"),
        InlineKeyboardButton(text="🔄 وضعیت سرویس", callback_data="adm:status"),
    )
    kb.row(
        InlineKeyboardButton(text="📣 پیام همگانی", callback_data="adm:broadcast"),
        InlineKeyboardButton(text="🧹 پاکسازی tmp", callback_data="adm:cleanup"),
    )
    kb.row(InlineKeyboardButton(text="❌ بستن", callback_data="adm:close"))
    return kb.as_markup()

def admin_settings_kb(settings: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    h = settings.get("max_video_height", "1080")
    cap = "ON" if settings.get("show_audio_separately") == "1" else "OFF"
    maint = settings.get("maintenance_mode", "0")
    kb.row(InlineKeyboardButton(text=f"🎞️ حداکثر کیفیت: {h}p", callback_data="adm:cfg:max_video_height"))
    kb.row(InlineKeyboardButton(text=f"🎧 ارسال صدای جدا: {cap}", callback_data="adm:cfg:show_audio_separately"))
    kb.row(InlineKeyboardButton(text=f"🛠️ حالت تعمیر: {'✅' if maint=='1' else '❌'}", callback_data="adm:cfg:maintenance_mode"))
    kb.row(InlineKeyboardButton(text="📝 کپشن پیش‌فرض", callback_data="adm:cfg:caption_template"))
    kb.row(InlineKeyboardButton(text="👋 پیام خوش‌آمد", callback_data="adm:cfg:welcome_message"))
    kb.row(InlineKeyboardButton(text="⏱️ حداکثر زمان ویدیو", callback_data="adm:cfg:max_duration_sec"))
    kb.row(InlineKeyboardButton(text="🚦 محدودیت ساعتی", callback_data="adm:cfg:rate_limit_per_hour"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_channels_kb(channels: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        cid, username, title, link, active = ch
        label = (title or username)[:18]
        status = "✅" if active else "⏸️"
        kb.row(
            InlineKeyboardButton(text=f"{status} {label}", callback_data="adm:ch:noop:{cid}"),
            InlineKeyboardButton(text="🔄", callback_data=f"adm:ch:toggle:{cid}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"adm:ch:del:{cid}"),
        )
    kb.row(InlineKeyboardButton(text="➕ افزودن کانال", callback_data="adm:ch:add"))
    kb.row(InlineKeyboardButton(text="💡 راهنما", callback_data="adm:ch:help"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_ads_kb(ads: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ad in ads:
        aid, text, photo, btn_text, btn_url, active, every = ad
        status = "✅" if active else "⏸️"
        kb.row(
            InlineKeyboardButton(text=f"{status} #{aid} هر {every} دانلود", callback_data=f"adm:ad:noop:{aid}"),
            InlineKeyboardButton(text="🔄", callback_data=f"adm:ad:toggle:{aid}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"adm:ad:del:{aid}"),
        )
    kb.row(InlineKeyboardButton(text="➕ افزودن تبلیغ", callback_data="adm:ad:add"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_users_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📋 20 کاربر اخیر", callback_data="adm:users:list:0"),
        InlineKeyboardButton(text="🔍 جستجو", callback_data="adm:users:search"),
    )
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_cookies_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="▶️ راهنمای کوکی", callback_data="adm:cookies:help"))
    kb.row(
        InlineKeyboardButton(text="📤 آپلود YouTube", callback_data="adm:cookies:up:youtube"),
        InlineKeyboardButton(text="📤 آپلود Instagram", callback_data="adm:cookies:up:instagram"),
    )
    kb.row(
        InlineKeyboardButton(text="📤 آپلود TikTok", callback_data="adm:cookies:up:tiktok"),
        InlineKeyboardButton(text="🗑️ حذف همه", callback_data="adm:cookies:clear"),
    )
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="adm:main")]])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data="adm:main")]])
