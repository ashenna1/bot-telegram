"""
Link detection & platform classification - extended to 9 platforms
"""
import re
from bot.config import YOUTUBE_RE, INSTAGRAM_RE, TIKTOK_RE, URL_RE, SPOTIFY_RE

YT_PATTERNS = [
    re.compile(r"youtube\.com/watch\?v=([^&\s]+)", re.I),
    re.compile(r"youtu\.be/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"youtube\.com/live/([A-Za-z0-9_\-]{6,})", re.I),
    re.compile(r"music\.youtube\.com/watch\?v=", re.I),
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
PIN_PATTERNS = [
    re.compile(r"pinterest\.com/pin/\d+", re.I),
    re.compile(r"pin\.it/[A-Za-z0-9]+", re.I),
    re.compile(r"pinterest\.[a-z]+/.*", re.I),
]
TW_PATTERNS = [
    re.compile(r"(twitter|x)\.com/\w+/status/\d+", re.I),
    re.compile(r"t\.co/[A-Za-z0-9]+", re.I),
]
FB_PATTERNS = [
    re.compile(r"facebook\.com/.*(video|watch|reel|share).*", re.I),
    re.compile(r"fb\.watch/[A-Za-z0-9_\-]+", re.I),
]
SC_PATTERNS = [
    re.compile(r"soundcloud\.com/[\w\-]+/[\w\-]+", re.I),
]
SP_PATTERNS = [
    re.compile(r"open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+", re.I),
    re.compile(r"spotify\.com/track/[A-Za-z0-9]+", re.I),
]
TH_PATTERNS = [
    re.compile(r"threads\.net/@[^/]+/post/[A-Za-z0-9_\-]+", re.I),
    re.compile(r"threads\.com/.*", re.I),
]

PLATFORM_MAP = {
    "youtube": (YT_PATTERNS, ["youtube", "youtu.be", "music.youtube"]),
    "instagram": (IG_PATTERNS, ["instagram.com"]),
    "tiktok": (TT_PATTERNS, ["tiktok.com"]),
    "pinterest": (PIN_PATTERNS, ["pinterest.com", "pin.it"]),
    "twitter": (TW_PATTERNS, ["twitter.com", "x.com", "t.co"]),
    "facebook": (FB_PATTERNS, ["facebook.com", "fb.watch"]),
    "soundcloud": (SC_PATTERNS, ["soundcloud.com"]),
    "spotify": (SP_PATTERNS, ["spotify.com"]),
    "threads": (TH_PATTERNS, ["threads.net", "threads.com"]),
}

def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    return URL_RE.findall(text)

def detect_platform(url: str) -> str | None:
    u = url.lower()
    for platform, (patterns, keywords) in PLATFORM_MAP.items():
        if any(p.search(u) for p in patterns):
            return platform
        if any(kw in u for kw in keywords):
            # extra guard: generic keyword hit but not regex; still likely
            # For youtube/instagram etc this is okay. For others need regex.
            # We'll trust keywords for short domains like pin.it, t.co, fb.watch
            if platform in ("pinterest", "twitter", "facebook"):
                # already covered by patterns; keywords alone enough for some
                pass
            # For main three, keyword is enough
            if platform in ("youtube", "instagram", "tiktok", "soundcloud"):
                return platform
    # Fallback for twitter/pinterest direct
    for platform, (patterns, keywords) in PLATFORM_MAP.items():
        if any(kw in u for kw in keywords):
            return platform
    return None

def find_first_supported_url(text: str) -> tuple[str | None, str | None]:
    urls = extract_urls(text)
    for u in urls:
        plat = detect_platform(u)
        if plat:
            u = u.rstrip(").,!?\"'»")
            return u, plat
    return None, None

def platform_emoji(platform: str) -> str:
    return {
        "youtube": "🔴",
        "instagram": "📸",
        "tiktok": "🎵",
        "pinterest": "📌",
        "twitter": "🐦",
        "facebook": "👥",
        "soundcloud": "🎧",
        "spotify": "💚",
        "threads": "🧵",
    }.get(platform, "🎬")

def platform_name_fa(platform: str) -> str:
    return {
        "youtube": "یوتیوب",
        "instagram": "اینستاگرام",
        "tiktok": "تیک‌تاک",
        "pinterest": "پینترست",
        "twitter": "توییتر",
        "facebook": "فیسبوک",
        "soundcloud": "ساندکلاد",
        "spotify": "اسپاتیفای",
        "threads": "تردز",
    }.get(platform, platform)

def is_audio_only_platform(platform: str) -> bool:
    return platform in ("soundcloud", "spotify")
