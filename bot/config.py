"""
MediODL Bot - Configuration
All runtime settings loaded from .env + DB (DB overrides defaults).
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
for p in [Path("/opt/mediodl-bot/.env"), BASE_DIR / ".env", BASE_DIR / ".env.example"]:
    if p.exists():
        load_dotenv(p, override=False)

def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)).strip())
    except Exception:
        return default

def _str(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or default).strip()

def _bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key, "")
    if not v:
        return default
    return v.lower() in ("1", "true", "yes", "on")

# ---- Core ----
BOT_TOKEN: str = _str("BOT_TOKEN", "")
BOT_NAME: str = _str("BOT_NAME", "لینک قاپ")
BOT_USERNAME: str = _str("BOT_USERNAME", "linkghap_bot")
DEFAULT_LANG: str = _str("DEFAULT_LANG", "fa")

_raw_admins = _str("ADMIN_IDS", "")
ADMIN_IDS: list[int] = []
if _raw_admins:
    for part in re.split(r"[,\s]+", _raw_admins):
        part = part.strip()
        if part.isdigit():
            ADMIN_IDS.append(int(part))

# ---- Paths ----
TMP_DIR = Path(_str("TMP_DIR", str(BASE_DIR / "tmp")))
DATABASE_PATH = Path(_str("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db")))
COOKIES_DIR = Path(_str("COOKIES_DIR", str(Path("/opt/mediodl-bot/cookies") if Path("/opt/mediodl-bot").exists() else BASE_DIR / "cookies")))
COOKIES_YT = COOKIES_DIR / "youtube.txt"
COOKIES_IG = COOKIES_DIR / "instagram.txt"
COOKIES_TT = COOKIES_DIR / "tiktok.txt"
COOKIES_PIN = COOKIES_DIR / "pinterest.txt"
COOKIES_TW = COOKIES_DIR / "twitter.txt"
COOKIES_FB = COOKIES_DIR / "facebook.txt"
COOKIES_SC = COOKIES_DIR / "soundcloud.txt"
COOKIES_SP = COOKIES_DIR / "spotify.txt"
COOKIES_TH = COOKIES_DIR / "threads.txt"

# ---- Limits ----
MAX_VIDEO_HEIGHT: int = _int("MAX_VIDEO_HEIGHT", 1080)
MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 2000)
MAX_DURATION_SEC: int = _int("MAX_DURATION_SEC", 3600)
RATE_LIMIT_PER_HOUR: int = _int("RATE_LIMIT_PER_HOUR", 20)
RATE_LIMIT_CONCURRENT: int = _int("RATE_LIMIT_CONCURRENT", 2)

# ---- Local Bot API (optional, for >50MB) ----
BOT_API_SERVER: str = _str("BOT_API_SERVER", "")
BOT_API_PORT: str = _str("BOT_API_PORT", "")
USE_LOCAL_API: bool = bool(BOT_API_SERVER)

LOG_LEVEL: str = _str("LOG_LEVEL", "INFO")

# ---- Feature flags (DB can override) ----
DEFAULT_SETTINGS = {
    "max_video_height": str(MAX_VIDEO_HEIGHT),
    "max_upload_mb": str(MAX_UPLOAD_MB),
    "max_duration_sec": str(MAX_DURATION_SEC),
    "rate_limit_per_hour": str(RATE_LIMIT_PER_HOUR),
    "caption_template": "🎬 {title}\n👁️ {view_count} بازدید | 👍 {like_count} لایک\n📺 {uploader}\n\n🤖 @{bot_username}",
    "show_audio_separately": "1",
    "auto_delete_hours": "0",
    "welcome_message": (
        "سلام {name} عزیز 👋\n\n"
        "من <b>{bot_name}</b> هستم — لینک‌قاپِ حرفه‌ای تو! 😎⚡️\n"
        "هر لینکی بفرستی، در یک چشم‌برهم‌زدن برات می‌قاپم:\n"
        "🎬 ویدیو با بهترین کیفیت + 🎧 صدای جدا\n\n"
        "📌 ۹ پلتفرم: یوتیوب، اینستاگرام، تیک‌تاک، پینترست، توییتر، فیسبوک، ساندکلاد، اسپاتیفای، تردز\n"
        "✨ فقط لینک بفرست — بقیه‌اش با من!"
    ),
    "force_join_enabled": "0",
    "maintenance_mode": "0",
    "maintenance_text": "🛠️ ربات در حال بروزرسانی است، لطفاً دقایقی دیگر تلاش کنید.",
    # Captcha / Anti-spam
    "captcha_enabled": "0",
    "captcha_mode": "emoji",  # emoji | math | both
    "captcha_timeout_sec": "120",
    "antispam_enabled": "1",
    "antispam_max_per_min": "5",
    "antispam_ban_minutes": "10",
    # Quality selection
    "quality_selection": "1",  # 1 = user picks, 0 = auto best
    # Log channel
    "log_channel": "",
    "log_to_admin_dm": "1",
    "log_new_users": "1",
    "log_downloads": "1",
    "log_errors": "1",
    "daily_report_enabled": "0",
    "daily_report_time": "09:00",
}

# ---- Runtime checks ----
IS_PRODUCTION = Path("/opt/mediodl-bot").exists()
VERSION = "1.1.0"

# Platform detection helpers
YOUTUBE_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/(watch\?v=|shorts/|embed/|v/)?[A-Za-z0-9_\-]{6,}", re.I)
YOUTUBE_SHORT_RE = re.compile(r"youtu\.be/|youtube\.com/(watch|shorts|embed)", re.I)
INSTAGRAM_RE = re.compile(r"(https?://)?(www\.)?instagram\.com/(p|reel|reels|stories|tv)/[A-Za-z0-9_\-./?=&%]+", re.I)
TIKTOK_RE = re.compile(r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/[^\s]+", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)

# Spotify handling (needs special search fallback)
SPOTIFY_RE = re.compile(r"https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+", re.I)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
