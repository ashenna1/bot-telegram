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

def random_compliment() -> str:
    compliments = [
        "دمت گرم که از ربات استفاده می‌کنی! 🔥",
        "تو واقعاً سلیقه‌ات حرف نداره 😎",
        "این ویدیو رو که دیدم گفتم حتماً بفرستم برات! 🎬",
        "یه انتخاب عالی دیگه! ✨",
        "ربات داره با عشق برات دانلود می‌کنه 💖",
        "لینک‌قاپ همیشه هواتو داره! ⚡️",
        "عالیه! اینم برات قاپیدم 😎",
    ]
    return random.choice(compliments)

def fun_greeting(name: str) -> str:
    greetings = [
        f"سلام {name} عزیز! 👋 حالت چطوره امروز؟ 😊",
        f"درود {name} جان! 🌟 آماده‌ای یه لینک بفرستی؟",
        f"هی {name}! 😎 لینک‌قاپ حاضر و آماده‌ست!",
        f"سلام سلام {name} 🎉 بیا یه ویدیو خفن دانلود کنیم!",
        f"به به {name} اومد! ⚡️ لینک‌قاپ در خدمتته!",
    ]
    return random.choice(greetings)

def spotify_to_search_query(meta: dict) -> str:
    title = meta.get("title") or meta.get("track") or ""
    artist = meta.get("artist") or meta.get("uploader") or ""
    if artist and title:
        return f"{artist} - {title}"
    return title or "music"
