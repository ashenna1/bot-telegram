"""
Inline keyboards - fun & friendly
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

def after_video_kb(platform: str, url: str, token: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎬 دانلود دوباره", callback_data=f"redl:{platform}"),
        InlineKeyboardButton(text="🔗 لینک اصلی", url=url[:200]),
    )
    kb.row(
        InlineKeyboardButton(text="📤 اشتراک‌گذاری", switch_inline_query=url[:100]),
    )
    return kb.as_markup()

def captcha_kb(options: list[str], correct: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Shuffle already done; just make buttons
    for i, opt in enumerate(options):
        # Use callback with index; correct hidden
        # We encode as captcha:idx where idx of correct? But need to hide correct.
        # Instead send captcha_pick:opt
        kb.button(text=opt, callback_data=f"captcha:{opt}")
    kb.adjust(2)
    return kb.as_markup()

def quality_kb(token: str, platform: str, has_audio: bool = True) -> InlineKeyboardMarkup:
    """Quality selection keyboard"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎬 1080p (بهترین)", callback_data=f"q:1080:{token}"),
        InlineKeyboardButton(text="🎬 720p", callback_data=f"q:720:{token}"),
    )
    kb.row(
        InlineKeyboardButton(text="🎬 480p (کم‌حجم)", callback_data=f"q:480:{token}"),
        InlineKeyboardButton(text="🎧 فقط صدا", callback_data=f"q:audio:{token}"),
    )
    if has_audio:
        kb.row(InlineKeyboardButton(text="✨ ویدیو + صدا (هر دو)", callback_data=f"q:both:{token}"))
    kb.row(InlineKeyboardButton(text="❌ لغو", callback_data=f"q:cancel:{token}"))
    return kb.as_markup()

# ---------- Admin ----------
def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 آمار پیشرفته", callback_data="adm:stats"),
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
    kb.row(
        InlineKeyboardButton(text="🛡️ کپچا & ضداسپم", callback_data="adm:captcha"),
        InlineKeyboardButton(text="📢 کانال لاگ", callback_data="adm:logchan"),
    )
    kb.row(
        InlineKeyboardButton(text="🗑️ حذف خودکار", callback_data="adm:autodel"),
        InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm:update"),
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
    kb.row(InlineKeyboardButton(text="🎚️ انتخاب کیفیت: " + ("✅" if settings.get("quality_selection")=="1" else "❌"), callback_data="adm:cfg:quality_selection"))
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
        InlineKeyboardButton(text="📤 YouTube", callback_data="adm:cookies:up:youtube"),
        InlineKeyboardButton(text="📤 Instagram", callback_data="adm:cookies:up:instagram"),
    )
    kb.row(
        InlineKeyboardButton(text="📤 TikTok", callback_data="adm:cookies:up:tiktok"),
        InlineKeyboardButton(text="📤 Pinterest", callback_data="adm:cookies:up:pinterest"),
    )
    kb.row(
        InlineKeyboardButton(text="📤 Twitter/X", callback_data="adm:cookies:up:twitter"),
        InlineKeyboardButton(text="📤 Facebook", callback_data="adm:cookies:up:facebook"),
    )
    kb.row(
        InlineKeyboardButton(text="📤 SoundCloud", callback_data="adm:cookies:up:soundcloud"),
        InlineKeyboardButton(text="📤 Spotify", callback_data="adm:cookies:up:spotify"),
    )
    kb.row(
        InlineKeyboardButton(text="📤 Threads", callback_data="adm:cookies:up:threads"),
        InlineKeyboardButton(text="🗑️ حذف همه", callback_data="adm:cookies:clear"),
    )
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_captcha_kb(settings: dict) -> InlineKeyboardMarkup:
    enabled = settings.get("captcha_enabled", "0") == "1"
    antispam = settings.get("antispam_enabled", "1") == "1"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"🛡️ کپچا: {'✅' if enabled else '❌'}", callback_data="adm:cfg:captcha_enabled"))
    kb.row(InlineKeyboardButton(text=f"🧮 حالت: {settings.get('captcha_mode','emoji')}", callback_data="adm:cfg:captcha_mode"))
    kb.row(InlineKeyboardButton(text=f"🚦 ضداسپم: {'✅' if antispam else '❌'}", callback_data="adm:cfg:antispam_enabled"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_logchan_kb(settings: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    to_admin = settings.get("log_to_admin_dm", "1") == "1"
    daily = settings.get("daily_report_enabled", "0") == "1"
    kb.row(InlineKeyboardButton(text=f"👑 به ادمین: {'✅' if to_admin else '❌'}", callback_data="adm:cfg:log_to_admin_dm"))
    kb.row(InlineKeyboardButton(text=f"📅 گزارش روزانه: {'✅' if daily else '❌'}", callback_data="adm:cfg:daily_report_enabled"))
    kb.row(InlineKeyboardButton(text="📢 تنظیم کانال لاگ", callback_data="adm:logchan:set"))
    kb.row(InlineKeyboardButton(text="🗑️ حذف کانال لاگ", callback_data="adm:logchan:clear"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def admin_autodel_kb(settings: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    cur = settings.get("auto_delete_hours", "0")
    kb.row(InlineKeyboardButton(text=f"🗑️ حذف خودکار: {cur} ساعت (0=خاموش)", callback_data="adm:cfg:auto_delete_hours"))
    kb.row(
        InlineKeyboardButton(text="⏰ 1 ساعت", callback_data="adm:autodel:set:1"),
        InlineKeyboardButton(text="⏰ 6 ساعت", callback_data="adm:autodel:set:6"),
    )
    kb.row(
        InlineKeyboardButton(text="⏰ 24 ساعت", callback_data="adm:autodel:set:24"),
        InlineKeyboardButton(text="❌ خاموش", callback_data="adm:autodel:set:0"),
    )
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm:main"))
    return kb.as_markup()

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="adm:main")]])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data="adm:main")]])
