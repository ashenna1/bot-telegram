"""
General helpers
"""
import time
import re
import html
import random
from pathlib import Path

def fmt_duration(sec: int | float | None) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def fmt_size(num: int | float | None) -> str:
    if not num or num <= 0:
        return "—"
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"

def fmt_views(n) -> str:
    if n is None:
        return "—"
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)

def escape_html(s: str) -> str:
    return html.escape(s or "")

def safe_filename(s: str, max_len=80) -> str:
    s = re.sub(r'[\\/*?:"<>|]', "", s or "video")
    s = s.strip().replace("\n", " ").strip()
    return s[:max_len] or "video"

def build_caption(meta: dict, template: str, bot_username: str) -> str:
    title = (meta.get("title") or "بدون عنوان").strip()
    uploader = meta.get("uploader") or meta.get("channel") or ""
    view_count = fmt_views(meta.get("view_count"))
    like_count = fmt_views(meta.get("like_count"))
    duration = fmt_duration(meta.get("duration"))
    data = {
        "title": title[:300],
        "uploader": uploader,
        "view_count": view_count,
        "like_count": like_count,
        "duration": duration,
        "bot_username": bot_username or "MediODL",
    }
    try:
        return template.format(**data)
    except Exception:
        return f"🎬 {title}\n👁️ {view_count} بازدید | 👍 {like_count}\n⏱️ {duration}\n📺 {uploader}"

def progress_bar(percent: float, width=12) -> str:
    filled = int(percent / 100 * width)
    return "●" * filled + "○" * (width - filled)

def truncate(s: str, n=4000) -> str:
    if len(s) <= n:
        return s
    return s[:n] + "…"

# ---- Fun helpers ----
FUN_COMPLIMENTS = [
    "دمت گرم که از ربات استفاده می‌کنی! 🔥",
    "تو واقعاً سلیقه‌ات حرف نداره 😎",
    "این ویدیو رو که دیدم گفتم حتماً بفرستم برات! 🎬",
    "یه انتخاب عالی دیگه! ✨",
    "ربات داره با عشق برات دانلود می‌کنه 💖",
]

FUN_FACTS = [
    "💡 می‌دونستی؟ هر روز بیش از ۱ میلیارد ساعت ویدیو در یوتیوب دیده می‌شه!",
    "🎵 تیک‌تاک رو یه جوون ۲۰ ساله تو ۲۰۱۶ ساخت و الان غوغاست!",
    "📌 پینترست اول به عنوان دفتر ایده برای عروسی ساخته شد!",
    "🐦 توییتر اولش می‌خواست فقط پیامک ۱۴۰ کاراکتری باشه!",
    "🎧 ساندکلاد جاییه که خیلی از ستاره‌های امروز اولش معروف شدن!",
]

FUN_JOKES = [
    "😂 یه ربات به رفیقش میگه: چرا ناراحتی؟ میگه: وای‌فای ندارم، افسرده شدم!",
    "🤖 ربات عاشق شد؟ حالا هر روز بهش میگه: I love you 3000... bytes!",
    "😄 چرا کامپیوتر هیچ‌وقت گرسنه نمی‌شه؟ چون همیشه یه عالمه چیپس داره! (Chips 😜)",
]

def random_compliment() -> str:
    return random.choice(FUN_COMPLIMENTS)

def random_fact() -> str:
    return random.choice(FUN_FACTS)

def random_joke() -> str:
    return random.choice(FUN_JOKES)

def fun_greeting(name: str) -> str:
    greetings = [
        f"سلام {name} عزیز! 👋 حالت چطوره امروز؟ 😊",
        f"درود {name} جان! 🌟 آماده‌ای یه لینک بفرستی؟",
        f"هی {name}! 😎 ربات باحال حاضر و آماده‌ست!",
        f"سلام سلام {name} 🎉 بیا یه ویدیو خفن دانلود کنیم!",
    ]
    return random.choice(greetings)

# ---- Spotify helper (search fallback) ----
def spotify_to_search_query(meta: dict) -> str:
    """Convert Spotify track meta to YouTube search query."""
    title = meta.get("title") or meta.get("track") or ""
    artist = meta.get("artist") or meta.get("uploader") or ""
    if artist and title:
        return f"{artist} - {title}"
    return title or "music"
