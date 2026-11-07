"""
yt-dlp wrapper - supports 9 platforms, robust YouTube handling
Fix: "No video formats found" by using permissive fallback, updated youtube clients, PO-token ready
"""
import asyncio
import json
import time
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
import logging

from bot.config import (
    MAX_VIDEO_HEIGHT, MAX_DURATION_SEC, TMP_DIR, COOKIES_DIR,
    COOKIES_YT, COOKIES_IG, COOKIES_TT,
    COOKIES_PIN, COOKIES_TW, COOKIES_FB, COOKIES_SC, COOKIES_SP, COOKIES_TH
)

log = logging.getLogger("downloader")

def _find_bin(name: str) -> str:
    for p in [Path("/opt/mediodl-bot/venv/bin") / name, Path("/usr/local/bin") / name, Path("/usr/bin") / name]:
        if p.exists():
            return str(p)
    found = shutil.which(name)
    return found or name

YTDLP_BIN = _find_bin("yt-dlp")
FFMPEG_BIN = _find_bin("ffmpeg")
DENO_BIN = _find_bin("deno")
log.info("Bins: yt-dlp=%s ffmpeg=%s deno=%s", YTDLP_BIN, FFMPEG_BIN, DENO_BIN)

def _safe_decode(b: bytes | None) -> str:
    """Decode subprocess output safely — fixes 'utf-8 codec can't decode byte 0xac'."""
    if not b:
        return ""
    # yt-dlp can emit non-utf8 bytes (cookies, headers, Persian filenames, Windows-1256)
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return b.decode(enc, errors="replace")
        except Exception:
            continue
    return b.decode("latin-1", errors="replace")

def _cookie_args(platform: str) -> list[str]:
    mapping = {
        "youtube": COOKIES_YT,
        "instagram": COOKIES_IG,
        "tiktok": COOKIES_TT,
        "pinterest": COOKIES_PIN,
        "twitter": COOKIES_TW,
        "facebook": COOKIES_FB,
        "soundcloud": COOKIES_SC,
        "spotify": COOKIES_SP,
        "threads": COOKIES_TH,
    }
    p = mapping.get(platform)
    if p and p.exists() and p.stat().st_size > 10:
        return ["--cookies", str(p)]
    generic = COOKIES_DIR / "cookies.txt"
    if generic.exists() and generic.stat().st_size > 10:
        return ["--cookies", str(generic)]
    return []

def _base_opts(platform: str, for_probe: bool = False) -> list[str]:
    """
    Base opts tuned for 2025 YouTube SABR + JS challenge.
    - player_client includes android,web,default to ensure at least one returns formats
    - impersonate chrome for bypass
    - PO token support: if cookies/youtube_pot.txt exists, pass as extractor-args
    """
    opts = [
        "--no-playlist",
        "--no-warnings",
        "--ignore-no-formats-error",
        "--extractor-retries", "3",
        "--fragment-retries", "3",
        "--socket-timeout", "20",
        "--concurrent-fragments", "3",
        "--retries", "2",
        "--no-check-certificates",
        "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--remote-components", "ejs:github",
    ]
    # YouTube extractor args: include default player + skip webpage configs for speed
    if platform == "youtube":
        # Important: include multiple clients so if one fails (No formats) another succeeds
        # android/creator clients often bypass PO token requirement
        opts += ["--extractor-args", "youtube:player_client=android,web,default;player_skip=webpage,configs;po_token=web+env"]
        # Enable PO token file if present (advanced)
        pot = COOKIES_DIR / "youtube_pot.txt"
        if pot.exists():
            try:
                token = pot.read_text(encoding="utf-8", errors="replace").strip()
                if token:
                    opts += ["--extractor-args", f"youtube:po_token={token}"]
            except Exception:
                pass
        opts += ["--impersonate", "chrome"]
    else:
        opts += ["--extractor-args", "youtube:player_client=android,web,default"]
        if platform in ("tiktok", "twitter", "facebook", "instagram"):
            opts += ["--impersonate", "chrome"]

    if Path(DENO_BIN).exists():
        opts += ["--js-runtimes", f"deno:{DENO_BIN}"]
    else:
        opts += ["--js-runtimes", "deno"]

    opts += _cookie_args(platform)
    return opts

# ---------- Helpers for friendly errors ----------
def _friendly_probe_error(platform: str, msg: str) -> str:
    low = msg.lower()
    # handle raw decode errors that previously crashed with "'utf-8' codec can't decode byte 0xac"
    if "codec can't decode" in low or "can't decode byte" in low or "invalid start byte" in low:
        return (
            "⚠️ خطای انکودینگ در پاسخ یوتیوب (معمولاً به خاطر کوکی خراب یا yt-dlp قدیمی).\n"
            "• روی سرور: <code>mediodl update</code> بزن\n"
            "• کوکی یوتیوب را دوباره با فرمت Netscape (Get cookies.txt LOCALLY) آپلود کن\n"
            "• اگر کوکی از مرورگر فارسی گرفتی، مطمئن شو فایل utf-8 باشد\n"
            f"جزئیات: {msg[:300]}"
        )
    if "private" in low or "login" in low or "sign in" in low:
        return "🔒 این محتوا خصوصی است یا نیاز به ورود دارد. کوکی یوتیوب را در پنل ادمین بروزرسانی کن."
    if "unsupported url" in low:
        return f"❌ لینک پشتیبانی نمی‌شود (پلتفرم: {platform})."
    if "video unavailable" in low or "not available" in low:
        return "❌ ویدیو در دسترس نیست یا حذف شده است."
    if "no video formats found" in low:
        return (
            "⚠️ یوتیوب فرمت ویدیو را برنگرداند.\n"
            "• معمولاً به خاطر تغییر Player یوتیوب یا نبود PO Token است.\n"
            "• روی سرور: <code>mediodl update</code> بزن تا yt-dlp آپدیت شود.\n"
            "• اگر باز هم نشد، در پنل ادمین → 🍪 کوکی یوتیوب را دوباره آپلود کن (Get cookies.txt LOCALLY).\n"
            f"جزئیات: {msg[:300]}"
        )
    if "sign in to confirm" in low or "precondition check failed" in low:
        return "🔒 یوتیوب احراز سن/بات را می‌خواهد. کوکی معتبر آپلود کن."
    return f"❌ خطا در بررسی لینک: {msg[:400]}"

def _friendly_download_error(platform: str, msg: str) -> str:
    low = msg.lower()
    if "codec can't decode" in low or "can't decode byte" in low:
        return (
            "⚠️ خطای انکودینگ — کوکی یا خروجی yt-dlp خراب است.\n"
            "کوکی را دوباره با افزونه Get cookies.txt LOCALLY بگیر و آپلود کن، سپس <code>mediodl update</code> بزن."
        )
    if "private" in low or "login" in low:
        return "🔒 محتوا خصوصی است. با ادمین تماس بگیر."
    if "no video formats found" in low:
        return (
            "⚠️ یوتیوب هیچ فرمتی برنگرداند (No video formats found).\n"
            "ربات خودکار با تنظیمات جایگزین دوباره تلاش می‌کند...\n"
            "اگر تکرار شد: <code>mediodl update</code> و آپلود کوکی یوتیوب."
        )
    if "no such file" in low or "not found" in low:
        if "yt-dlp" in low:
            return f"❌ yt-dlp یافت نشد ({YTDLP_BIN}). دستور <code>mediodl update</code> را اجرا کن."
        if "ffmpeg" in low:
            return "❌ ffmpeg نصب نیست. روی سرور: <code>apt install ffmpeg</code>"
    if "unable to extract" in low:
        return f"⚠️ یوتیوب ساختار صفحه را تغییر داده. لطفاً ربات را آپدیت کن.\n{msg[:400]}"
    return f"❌ خطا در دانلود ویدیو:\n{msg[:600]}"

async def probe_info(url: str, platform: str) -> Dict[str, Any]:
    cmd = [YTDLP_BIN, "--dump-json", "--no-download", "--no-playlist"] + _base_opts(platform, for_probe=True) + [url]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=35)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("⏱️ زمان بررسی لینک تمام شد. دوباره تلاش کنید.")

    if proc.returncode != 0:
        msg = (_safe_decode(err) or _safe_decode(out))[:2000]
        log.warning("probe failed %s platform=%s: %s", url, platform, msg)
        if platform == "spotify":
            raise RuntimeError("SPOTIFY_SEARCH_FALLBACK")
        low = msg.lower()
        if "no video formats found" in low:
            raise RuntimeError(_friendly_probe_error(platform, msg))
        raise RuntimeError(_friendly_probe_error(platform, msg))

    try:
        text = _safe_decode(out)
        return json.loads(text)
    except UnicodeDecodeError as e:
        log.warning("probe json decode error: %s", e)
        raise RuntimeError(
            "⚠️ خطای انکودینگ در پاسخ یوتیوب (byte 0xac). کوکی خراب یا yt-dlp قدیمی است — "
            "<code>mediodl update</code> بزن و کوکی یوتیوب را دوباره آپلود کن."
        )
    except Exception as e:
        log.warning("probe json parse error: %s out=%s", e, _safe_decode(out)[:500])
        raise RuntimeError(f"❌ پاسخ نامعتبر از دانلودر: {e}")

async def download_cover(url: str, platform: str, workdir: Path) -> Path | None:
    """Fetch the platform's thumbnail with the same cookies as video downloads.

    Re-extract on demand because CDN thumbnail URLs (notably Instagram's) expire.
    The caller owns and removes workdir after the Telegram upload.
    """
    cmd = [YTDLP_BIN, "--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg",
           "-o", str(workdir / "cover.%(ext)s")] + _base_opts(platform) + ["--", url]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        log.warning("cover download failed for %s: %s", platform, _safe_decode(err)[-500:])
        raise RuntimeError("دریافت کاور ممکن نشد. لطفاً دوباره تلاش کن.")
    cover = workdir / "cover.jpg"
    if cover.is_file() and cover.stat().st_size > 0:
        return cover
    return None

def _build_format(max_h: int, audio_only: bool = False) -> str:
    """
    Build format string with progressive fallbacks.
    The old string was too strict on ext=mp4 which fails when only webm available.
    New chain tries mp4 first, then any ext, then best overall.
    """
    if audio_only:
        return "bestaudio/best"
    # Try mp4+ m4a first (best compatibility for Telegram), then any video+audio, then single best
    # Also include webm fallback explicitly
    fmt = (
        f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_h}][ext=mp4]+bestaudio/"
        f"bestvideo[height<={max_h}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_h}]+bestaudio/"
        f"best[height<={max_h}]/"
        f"bestaudio+bestvideo/"
        f"best"
    )
    return fmt

async def download_media(url: str, platform: str, max_height: int | None = None, workdir: Path | None = None, audio_only: bool = False) -> Dict[str, Any]:
    max_h = max_height or MAX_VIDEO_HEIGHT
    uid = uuid.uuid4().hex[:10]
    base = (workdir or TMP_DIR) / f"dl_{uid}"
    base.mkdir(parents=True, exist_ok=True)

    # 1) Probe
    try:
        meta = await probe_info(url, platform)
    except RuntimeError as e:
        # Special Spotify fallback
        if "SPOTIFY_SEARCH_FALLBACK" in str(e):
            raise
        raise

    duration = meta.get("duration") or 0
    if duration and duration > MAX_DURATION_SEC:
        raise RuntimeError(f"⏱️ ویدیو خیلی طولانی است ({int(duration//60)} دقیقه). حداکثر {MAX_DURATION_SEC//60} دقیقه مجاز است.")

    # Audio-only shortcut
    is_audio_platform = platform in ("soundcloud", "spotify")
    if audio_only or (is_audio_platform and platform == "soundcloud"):
        out_tmpl = str(base / "%(title).80s [%(id)s].%(ext)s")
        cmd_audio_dl = [
            "nice", "-n", "10", YTDLP_BIN,
            "-f", _build_format(max_h, audio_only=True),
            "-o", out_tmpl,
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
            "--no-playlist",
            "--concurrent-fragments", "3",
        ] + _base_opts(platform) + [url]
        log.info("Downloading audio-only: %s", url)
        proc = await asyncio.create_subprocess_exec(*cmd_audio_dl, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("⏱️ دانلود صدا خیلی طول کشید.")
        if proc.returncode != 0:
            msg = (_safe_decode(err) or _safe_decode(out))[:1000]
            raise RuntimeError(_friendly_download_error(platform, msg))
        audio_cands = sorted(base.glob("*"), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        audio_cands = [p for p in audio_cands if p.suffix.lower() in (".mp3", ".m4a", ".opus", ".ogg", ".webm") and p.stat().st_size > 1024]
        if not audio_cands:
            raise RuntimeError("❌ فایل صوتی یافت نشد.")
        audio_path = audio_cands[0]
        return {
            "meta": meta,
            "video_path": None,
            "audio_path": audio_path,
            "tmp_dir": base,
            "title": meta.get("title", ""),
            "duration": meta.get("duration"),
            "uploader": meta.get("uploader") or meta.get("channel") or "",
            "view_count": meta.get("view_count"),
            "like_count": meta.get("like_count"),
            "thumbnail": meta.get("thumbnail"),
        }

    # 2) Video download with retry strategy
    out_tmpl = str(base / "%(title).80s [%(id)s].%(ext)s")
    # First attempt: permissive format
    fmt1 = _build_format(max_h)
    # Second attempt (fallback if No formats): pure best (no height filter)
    fmt2 = "bestvideo+bestaudio/best"

    for attempt, video_fmt in enumerate([fmt1, fmt2], start=1):
        cmd_video = [
            "nice", "-n", "10", YTDLP_BIN,
            "-f", video_fmt,
            "--merge-output-format", "mp4",
            "-o", out_tmpl,
            "--embed-metadata",
            "--no-playlist",
            "--concurrent-fragments", "3",
        ] + _base_opts(platform) + [url]

        log.info("Downloading video attempt %d/%d: %s fmt=%s", attempt, 2, url, video_fmt)
        proc = await asyncio.create_subprocess_exec(*cmd_video, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("⏱️ دانلود ویدیو خیلی طول کشید (تایم‌اوت).")

        if proc.returncode == 0:
            break  # success, go to file discovery
        else:
            msg = (_safe_decode(err) or _safe_decode(out))[:2000]
            low = msg.lower()
            log.warning("download attempt %d failed: %s", attempt, msg[:500])
            # If it's No video formats and we have another attempt, retry
            if "no video formats found" in low and attempt == 1:
                log.info("Retrying youtube with fallback format %s", fmt2)
                continue
            # If private/login, don't retry
            if "private" in low or "login" in low:
                raise RuntimeError("🔒 محتوا خصوصی است. لطفاً با ادمین تماس بگیرید.")
            if "no such file" in low or "not found" in low:
                raise RuntimeError(_friendly_download_error(platform, msg))
            # For other errors on last attempt, raise
            if attempt == 2:
                raise RuntimeError(_friendly_download_error(platform, msg))

    # File discovery
    video_cands = sorted(base.glob("*"), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    video_files = [p for p in video_cands if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4a") and p.stat().st_size > 1024]
    # Also handle case where yt-dlp produced separate video/audio not merged (mp4 may not exist)
    if not video_files:
        # Debug list
        all_files = list(base.glob("*"))
        log.warning("No video file found, dir contents: %s", all_files)
        raise RuntimeError("❌ فایل ویدیویی یافت نشد. فرمت درخواستی موجود نبود — کیفیت دیگری انتخاب کن.")

    video_path = video_files[0]
    # If file is webm and we need mp4, ffmpeg merge already done but keep as is; Telegram accepts webm as video? Convert if needed?
    meta["filepath"] = str(video_path)
    meta["filesize"] = video_path.stat().st_size

    # 3) Extract audio via ffmpeg
    audio_path: Path | None = None
    # Only extract if video is indeed video (has video stream)
    try:
        audio_out = base / (video_path.stem + ".mp3")
        cmd_audio = ["nice", "-n", "12", FFMPEG_BIN, "-y", "-i", str(video_path), "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-map_metadata", "0", "-id3v2_version", "3", str(audio_out)]
        proc2 = await asyncio.create_subprocess_exec(*cmd_audio, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            o2, e2 = await asyncio.wait_for(proc2.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc2.kill()
            raise
        if proc2.returncode == 0 and audio_out.exists() and audio_out.stat().st_size > 1024:
            audio_path = audio_out
        else:
            audio_out2 = base / (video_path.stem + ".m4a")
            cmd_audio2 = ["nice", "-n", "12", FFMPEG_BIN, "-y", "-i", str(video_path), "-vn", "-c:a", "aac", "-b:a", "128k", str(audio_out2)]
            proc3 = await asyncio.create_subprocess_exec(*cmd_audio2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            o3, e3 = await asyncio.wait_for(proc3.communicate(), timeout=120)
            if proc3.returncode == 0 and audio_out2.exists():
                audio_path = audio_out2
    except Exception as e:
        log.warning("Audio extract failed: %s", e)

    return {
        "meta": meta,
        "video_path": video_path,
        "audio_path": audio_path,
        "tmp_dir": base,
        "title": meta.get("title", ""),
        "duration": meta.get("duration"),
        "uploader": meta.get("uploader") or meta.get("channel") or "",
        "view_count": meta.get("view_count"),
        "like_count": meta.get("like_count"),
        "thumbnail": meta.get("thumbnail"),
    }

async def download_spotify_via_search(spotify_url: str, workdir: Path | None = None) -> Dict[str, Any]:
    meta = await probe_info(spotify_url, "spotify")
    query = meta.get("title") or spotify_url
    search_url = f"ytsearch1:{query}"
    log.info("Spotify fallback search: %s", search_url)
    return await download_media(search_url, "youtube", workdir=workdir)

def cleanup_tmp(path: Path):
    try:
        if not path or not path.exists():
            return
        if TMP_DIR.resolve() not in path.resolve().parents and path.resolve() != TMP_DIR.resolve():
            if path.is_file():
                path.unlink(missing_ok=True)
                return
            return
        if path.is_file():
            path.unlink(missing_ok=True)
        else:
            import shutil
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

async def periodic_cleanup():
    while True:
        try:
            now = time.time()
            for p in TMP_DIR.glob("dl_*"):
                try:
                    if now - p.stat().st_mtime > 7200:
                        cleanup_tmp(p)
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(3600)
