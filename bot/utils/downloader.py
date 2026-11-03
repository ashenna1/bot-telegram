"""
yt-dlp wrapper - supports 9 platforms, absolute paths for reliability (fixes yt-dlp not found)
"""
import asyncio
import json
import os
import subprocess
import time
import uuid
import re
import shutil
from pathlib import Path
from typing import Dict, Any
import logging

from bot.config import (
    MAX_VIDEO_HEIGHT, MAX_DURATION_SEC, TMP_DIR, COOKIES_DIR,
    COOKIES_YT, COOKIES_IG, COOKIES_TT,
    COOKIES_PIN, COOKIES_TW, COOKIES_FB, COOKIES_SC, COOKIES_SP, COOKIES_TH
)

log = logging.getLogger("downloader")

# Absolute paths - fixes [Errno 2] No such file or directory: 'yt-dlp'
def _find_bin(name: str) -> str:
    # Prefer venv bin
    for p in [Path("/opt/mediodl-bot/venv/bin") / name, Path("/usr/local/bin") / name, Path("/usr/bin") / name]:
        if p.exists():
            return str(p)
    found = shutil.which(name)
    return found or name

YTDLP_BIN = _find_bin("yt-dlp")
FFMPEG_BIN = _find_bin("ffmpeg")
DENO_BIN = _find_bin("deno")

# For diagnostics
log.info("Bins: yt-dlp=%s ffmpeg=%s deno=%s", YTDLP_BIN, FFMPEG_BIN, DENO_BIN)

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
    # Also check legacy per-domain generic
    return []

def _base_opts(platform: str) -> list[str]:
    opts = [
        "--no-playlist",
        "--no-warnings",
        "--ignore-no-formats-error",
        "--extractor-retries", "2",
        "--fragment-retries", "2",
        "--socket-timeout", "15",
        "--concurrent-fragments", "3",
        "--retries", "2",
        "--no-check-certificates",
        "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--extractor-args", "youtube:player_client=android,web",
        "--remote-components", "ejs:github",
    ]
    # Deno for JS challenge
    if Path(DENO_BIN).exists():
        opts += ["--js-runtimes", f"deno:{DENO_BIN}"]
    else:
        opts += ["--js-runtimes", "deno"]
    if platform == "tiktok":
        opts += ["--impersonate", "chrome"]
    # Spotify needs special handling - we search YouTube instead
    # Facebook/Twitter may need extra
    opts += _cookie_args(platform)
    return opts

async def probe_info(url: str, platform: str) -> Dict[str, Any]:
    """Light probe without downloading."""
    # Spotify: probe via search fallback
    if platform == "spotify":
        # Try to get metadata via yt-dlp (it can extract meta but not media)
        # We still try yt-dlp first, fallback to search
        pass

    cmd = [YTDLP_BIN, "--dump-json", "--no-download", "--no-playlist"] + _base_opts(platform) + [url]
    # If Spotify, add workaround: if probe fails we do search
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("⏱️ زمان بررسی لینک تمام شد. دوباره تلاش کنید.")

    if proc.returncode != 0:
        msg = (err.decode() or out.decode())[:2000]
        log.warning("probe failed %s: %s", url, msg)
        low = msg.lower()
        if platform == "spotify":
            # Fallback: search YouTube for spotify track
            # Extract track id and search
            try:
                # Try to search using yt-dlp search
                # We'll let caller handle by raising with hint
                raise RuntimeError("SPOTIFY_SEARCH_FALLBACK")
            except RuntimeError:
                raise
        if "private" in low or "login" in low or "sign in" in low:
            raise RuntimeError("🔒 این محتوا خصوصی است یا نیاز به ورود دارد. کوکی‌ها را در پنل ادمین بروزرسانی کنید.")
        if "unsupported url" in low:
            # Provide friendly for new platforms
            raise RuntimeError(f"❌ لینک پشتیبانی نمی‌شود. پلتفرم: {platform}. لینک دیگری امتحان کنید.")
        if "video unavailable" in low or "not available" in low:
            raise RuntimeError("❌ ویدیو در دسترس نیست یا حذف شده است.")
        raise RuntimeError(f"❌ خطا در بررسی لینک: {msg[:400]}")

    try:
        return json.loads(out.decode())
    except Exception as e:
        raise RuntimeError(f"❌ پاسخ نامعتبر از دانلودر: {e}")

async def download_media(url: str, platform: str, max_height: int | None = None, workdir: Path | None = None, audio_only: bool = False) -> Dict[str, Any]:
    """
    Downloads best video + separate audio (or audio_only for Spotify/SoundCloud)
    """
    max_h = max_height or MAX_VIDEO_HEIGHT
    uid = uuid.uuid4().hex[:10]
    base = (workdir or TMP_DIR) / f"dl_{uid}"
    base.mkdir(parents=True, exist_ok=True)

    # 1) Probe
    meta = await probe_info(url, platform)
    duration = meta.get("duration") or 0
    if duration and duration > MAX_DURATION_SEC:
        raise RuntimeError(f"⏱️ ویدیو خیلی طولانی است ({int(duration//60)} دقیقه). حداکثر {MAX_DURATION_SEC//60} دقیقه مجاز است.")

    is_audio_platform = platform in ("soundcloud", "spotify")
    # If Spotify search fallback was needed, meta may be empty; handle via search
    video_files: list[Path] = []

    if audio_only or (is_audio_platform and platform == "soundcloud"):
        # Audio-only download
        out_tmpl = str(base / "%(title).80s [%(id)s].%(ext)s")
        cmd_audio_dl = [
            "nice", "-n", "10", YTDLP_BIN,
            "-f", "bestaudio/best",
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
            raise RuntimeError(f"❌ خطا در دانلود صدا: {(err.decode() or out.decode())[:500]}")
        # Find audio
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

    # 2) Video download
    video_fmt = f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]/best"
    out_tmpl = str(base / "%(title).80s [%(id)s].%(ext)s")
    cmd_video = [
        "nice", "-n", "10", YTDLP_BIN,
        "-f", video_fmt,
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        "--embed-metadata",
        "--no-playlist",
        "--concurrent-fragments", "3",
    ] + _base_opts(platform) + [url]

    log.info("Downloading video: %s fmt=%s", url, video_fmt)
    proc = await asyncio.create_subprocess_exec(*cmd_video, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("⏱️ دانلود ویدیو خیلی طول کشید (تایم‌اوت).")

    if proc.returncode != 0:
        msg = (err.decode() or out.decode())[:2000]
        low = msg.lower()
        if "private" in low or "login" in low:
            raise RuntimeError("🔒 محتوا خصوصی است. لطفاً با ادمین تماس بگیرید.")
        # Check missing binaries
        if "no such file" in low or "not found" in low:
            if "yt-dlp" in low:
                raise RuntimeError(f"❌ باینری yt-dlp یافت نشد ({YTDLP_BIN}). دستور `mediodl update` را اجرا کن.")
            if "ffmpeg" in low:
                raise RuntimeError(f"❌ ffmpeg نصب نیست. روی سرور: apt install ffmpeg")
        raise RuntimeError(f"❌ خطا در دانلود ویدیو:\n{msg[:500]}")

    video_cands = sorted(base.glob("*"), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    video_files = [p for p in video_cands if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov") and p.stat().st_size > 1024]
    if not video_files:
        raise RuntimeError("❌ فایل ویدیویی یافت نشد.")

    video_path = video_files[0]
    meta["filepath"] = str(video_path)
    meta["filesize"] = video_path.stat().st_size

    # 3) Extract audio via ffmpeg
    audio_path: Path | None = None
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

# Spotify fallback via YouTube search (ytsearch)
async def download_spotify_via_search(spotify_url: str, workdir: Path | None = None) -> Dict[str, Any]:
    """For Spotify, search YouTube for track name and download that."""
    # First probe spotify to get title
    meta = await probe_info(spotify_url, "spotify")
    # meta title often like "Artist - Track"
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
