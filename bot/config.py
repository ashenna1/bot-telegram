"""
MediODL Bot - Configuration
All runtime settings loaded from .env + DB (DB overrides defaults).
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# In production /opt/mediodl-bot, in dev repo root
# Try /opt/mediodl-bot/.env first, then repo .env
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
BOT_NAME: str = _str("BOT_NAME", "MediODL")
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

# ---- Limits ----
MAX_VIDEO_HEIGHT: int = _int("MAX_VIDEO_HEIGHT", 1080)
MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 2000)
MAX_DURATION_SEC: int = _int("MAX_DURATION_SEC", 3600)  # 1h
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
    "show_audio_separately": "1",  # always deliver audio separately per spec
    "auto_delete_hours": "0",  # 0 = never
    "welcome_message": "سلام {name} عزیز 👋\n\nفقط لینک یوتیوب، اینستاگرام یا تیک‌تاک رو بفرست تا همین‌جا ویدیو با بهترین کیفیت + صدای جداگانه‌ش رو برات بفرستم. ✨\n\n📌 بدون نیاز به هیچ دستوری — فقط لینک!",
    "force_join_enabled": "0",
    "maintenance_mode": "0",
    "maintenance_text": "🛠️ ربات در حال بروزرسانی است، لطفاً دقایقی دیگر تلاش کنید.",
}

# ---- Runtime checks ----
IS_PRODUCTION = Path("/opt/mediodl-bot").exists()
VERSION = "1.0.0"

# Platform detection helpers
YOUTUBE_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/(watch\?v=|shorts/|embed/|v/)?[A-Za-z0-9_\-]{6,}", re.I)
YOUTUBE_SHORT_RE = re.compile(r"youtu\.be/|youtube\.com/(watch|shorts|embed)", re.I)
INSTAGRAM_RE = re.compile(r"(https?://)?(www\.)?instagram\.com/(p|reel|reels|stories|tv)/[A-Za-z0-9_\-./?=&%]+", re.I)
TIKTOK_RE = re.compile(r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/[^\s]+", re.I)
# Generic URL extractor
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
