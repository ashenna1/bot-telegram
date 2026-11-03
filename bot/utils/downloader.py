"""
yt-dlp wrapper - downloads best video + separate audio
Supports YouTube / Instagram / TikTok with cookie fallback.
Runs blocking yt-dlp in executor to keep event loop free.
Limits CPU/IO to avoid starving xray/x-ui.
"""
import asyncio
import json
import os
import subprocess
import time
import uuid
import re
from pathlib import Path
from typing import Dict, Any
import logging

from bot.config import (
    MAX_VIDEO_HEIGHT, MAX_DURATION_SEC, TMP_DIR, COOKIES_DIR,
    COOKIES_YT, COOKIES_IG, COOKIES_TT
)

log = logging.getLogger("downloader")

DENO_PATH = "/usr/local/bin/deno"

def _cookie_args(platform: str) -> list[str]:
    """Return yt-dlp cookie args if cookie file exists for platform."""
    mapping = {
        "youtube": COOKIES_YT,
        "instagram": COOKIES_IG,
        "tiktok": COOKIES_TT,
    }
    p = mapping.get(platform)
    if p and p.exists() and p.stat().st_size > 10:
        return ["--cookies", str(p)]
    # fallback: generic cookies.txt in cookies dir
    generic = COOKIES_DIR / "cookies.txt"
    if generic.exists() and generic.stat().st_size > 10:
        return ["--cookies", str(generic)]
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
        "--js-runtimes", f"deno:{DENO_PATH}" if Path(DENO_PATH).exists() else "deno",
        "--remote-components", "ejs:github",
    ]
    # TikTok needs impersonation иногда
    if platform == "tiktok":
        opts += ["--impersonate", "chrome"]
    opts += _cookie_args(platform)
    return opts

async def probe_info(url: str, platform: str) -> Dict[str, Any]:
    """Light probe without downloading - returns metadata dict."""
    cmd = ["yt-dlp", "--dump-json", "--no-download", "--no-playlist"] + _base_opts(platform) + [url]
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
        # Map common errors to Persian
        low = msg.lower()
        if "private" in low or "login" in low or "sign in" in low:
            raise RuntimeError("🔒 این محتوا خصوصی است یا نیاز به ورود دارد. کوکی‌ها را در پنل ادمین بروزرسانی کنید.")
        if "unsupported url" in low:
            raise RuntimeError("❌ لینک پشتیبانی نمی‌شود. فقط یوتیوب، اینستاگرام و تیک‌تاک.")
        if "video unavailable" in low or "not available" in low:
            raise RuntimeError("❌ ویدیو در دسترس نیست یا حذف شده است.")
        raise RuntimeError(f"❌ خطا در بررسی لینک: {msg[:400]}")

    try:
        return json.loads(out.decode())
    except Exception as e:
        raise RuntimeError(f"❌ پاسخ نامعتبر از دانلودر: {e}")

async def download_media(url: str, platform: str, max_height: int | None = None, workdir: Path | None = None) -> Dict[str, Any]:
    """
    Downloads:
      - best video (mp4, max_height limited) merged
      - audio extracted as mp3/m4a
    Returns dict with paths + meta.
    """
    max_h = max_height or MAX_VIDEO_HEIGHT
    uid = uuid.uuid4().hex[:10]
    base = (workdir or TMP_DIR) / f"dl_{uid}"
    base.mkdir(parents=True, exist_ok=True)

    # 1) Probe first to validate duration
    meta = await probe_info(url, platform)
    duration = meta.get("duration") or 0
    if duration and duration > MAX_DURATION_SEC:
        raise RuntimeError(f"⏱️ ویدیو خیلی طولانی است ({int(duration//60)} دقیقه). حداکثر {MAX_DURATION_SEC//60} دقیقه مجاز است.")

    # 2) Download video (best height <= max_h, fallback)
    # yt-dlp format: bestvideo[height<=H][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=H]+bestaudio/best
    video_fmt = f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]/best"
    out_tmpl = str(base / "%(title).80s [%(id)s].%(ext)s")
    # Use nice to limit CPU for coexistence with xray
    cmd_video = [
        "nice", "-n", "10",
        "yt-dlp",
        "-f", video_fmt,
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        "--embed-metadata",
        "--no-playlist",
        "--concurrent-fragments", "3",
    ] + _base_opts(platform) + [url]

    log.info("Downloading video: %s fmt=%s", url, video_fmt)
    proc = await asyncio.create_subprocess_exec(
        *cmd_video,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
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
        raise RuntimeError(f"❌ خطا در دانلود ویدیو:\n{msg[:500]}")

    # find downloaded video
    video_files = sorted(base.glob("*"), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    video_files = [p for p in video_files if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov") and p.stat().st_size > 1024]
    if not video_files:
        raise RuntimeError("❌ فایل ویدیویی یافت نشد.")

    video_path = video_files[0]
    meta["filepath"] = str(video_path)
    meta["filesize"] = video_path.stat().st_size

    # 3) Extract audio separately via ffmpeg (low CPU priority)
    audio_path: Path | None = None
    try:
        audio_out = base / (video_path.stem + ".mp3")
        cmd_audio = [
            "nice", "-n", "12",
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-c:a", "libmp3lame",
            "-q:a", "2",   # high quality VBR ~190k
            "-map_metadata", "0",
            "-id3v2_version", "3",
            str(audio_out),
        ]
        # fallback if libmp3lame missing
        proc2 = await asyncio.create_subprocess_exec(
            *cmd_audio,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            o2, e2 = await asyncio.wait_for(proc2.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc2.kill()
            raise

        if proc2.returncode == 0 and audio_out.exists() and audio_out.stat().st_size > 1024:
            audio_path = audio_out
        else:
            # try m4a AAC fallback
            audio_out2 = base / (video_path.stem + ".m4a")
            cmd_audio2 = ["nice", "-n", "12", "ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "aac", "-b:a", "128k", str(audio_out2)]
            proc3 = await asyncio.create_subprocess_exec(*cmd_audio2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            o3, e3 = await asyncio.wait_for(proc3.communicate(), timeout=120)
            if proc3.returncode == 0 and audio_out2.exists():
                audio_path = audio_out2
    except Exception as e:
        log.warning("Audio extract failed: %s", e)
        audio_path = None

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

def cleanup_tmp(path: Path):
    try:
        if not path or not path.exists():
            return
        # safety: only delete inside TMP_DIR
        if TMP_DIR.resolve() not in path.resolve().parents and path.resolve() != TMP_DIR.resolve():
            # single file in tmp?
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

# Housekeeping: clean old tmp dirs older than 2 hours
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
