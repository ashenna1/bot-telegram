"""
Link detection & platform classification
"""
import re
from bot.config import YOUTUBE_RE, INSTAGRAM_RE, TIKTOK_RE, URL_RE

# Extended patterns for edge URLs
YT_PATTERNS = [
    re.compile(r"youtube\.com/watch\?v=([^&\s]+)", re.I),
    re.compile(r"youtu\.be/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/live/([A-Za-z0-9_\-]{6,})", re.I),
]
IG_PATTERNS = [
    re.compile(r"instagram\.com/(p|reel|reels|tv)/([A-Za-z0-9_\-]+)", re.I),
    re.compile(r"instagram\.com/stories/[^/]+/\d+", re.I),
    re.compile(r"instagram\.com/share/[^/\s]+", re.I),
]
TT_PATTERNS = [
    re.compile(r"tiktok\.com/@[^/]+/video/\d+", re.I),
    re.compile(r"vm\.tiktok\.com/[A-Za-z0-9]+", re.I),
    re.compile(r"vt\.tiktok\.com/[A-Za-z0-9]+", re.I),
    re.compile(r"m\.tiktok\.com/.*", re.I),
]

def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    return URL_RE.findall(text)

def detect_platform(url: str) -> str | None:
    u = url.lower()
    if any(p.search(u) for p in YT_PATTERNS) or "youtube" in u or "youtu.be" in u:
        return "youtube"
    if "instagram.com" in u:
        return "instagram"
    if "tiktok.com" in u:
        return "tiktok"
    return None

def find_first_supported_url(text: str) -> tuple[str | None, str | None]:
    urls = extract_urls(text)
    for u in urls:
        plat = detect_platform(u)
        if plat:
            # clean trailing punctuation common in Telegram
            u = u.rstrip(").,!?\"'»")
            return u, plat
    return None, None

def platform_emoji(platform: str) -> str:
    return {"youtube": "🔴", "instagram": "📸", "tiktok": "🎵"}.get(platform, "🎬")

def platform_name_fa(platform: str) -> str:
    return {"youtube": "یوتیوب", "instagram": "اینستاگرام", "tiktok": "تیک‌تاک"}.get(platform, platform)
