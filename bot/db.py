"""
SQLite Database Layer (aiosqlite)
Zero external dependency, zero port conflict with 3x-ui/D_bot Postgres.
"""
import aiosqlite
import time
from pathlib import Path
from bot.config import DATABASE_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    fullname    TEXT,
    lang        TEXT DEFAULT 'fa',
    joined_at   INTEGER,
    last_seen   INTEGER,
    is_banned   INTEGER DEFAULT 0,
    downloads   INTEGER DEFAULT 0,
    is_verified INTEGER DEFAULT 0,
    verified_at INTEGER,
    warnings    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    chat_id     TEXT,
    title       TEXT,
    invite_link TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS ads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT,
    photo_file_id TEXT,
    button_text TEXT,
    button_url  TEXT,
    is_active   INTEGER DEFAULT 1,
    show_every  INTEGER DEFAULT 3,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS stats (
    date        TEXT PRIMARY KEY,
    downloads   INTEGER DEFAULT 0,
    users_new   INTEGER DEFAULT 0,
    requests    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS downloads_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    platform    TEXT,
    url         TEXT,
    title       TEXT,
    duration    INTEGER,
    file_size   INTEGER,
    success     INTEGER,
    error       TEXT,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS rate_limit (
    user_id     INTEGER,
    ts          INTEGER
);

CREATE TABLE IF NOT EXISTS captcha_state (
    user_id     INTEGER PRIMARY KEY,
    question    TEXT,
    answer      TEXT,
    attempts    INTEGER DEFAULT 0,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS auto_delete_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER,
    message_id  INTEGER,
    delete_at   INTEGER
);

-- For quality selection cache (short-lived, but persisted for simplicity)
CREATE TABLE IF NOT EXISTS pending_downloads (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER,
    url         TEXT,
    platform    TEXT,
    meta_json   TEXT,
    created_at  INTEGER
);
"""

async def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
        # Migrations for existing DBs (add columns if missing)
        # SQLite doesn't support IF NOT EXISTS for ALTER COLUMN, so try
        cols = await _get_columns(db, "users")
        if "is_verified" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
        if "verified_at" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN verified_at INTEGER")
        if "warnings" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0")
        await db.commit()
        from bot.config import DEFAULT_SETTINGS
        for k, v in DEFAULT_SETTINGS.items():
            await db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        await db.commit()

async def _get_columns(db, table: str) -> list[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
        return [r[1] for r in rows]

# --- Settings ---
async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))
        await db.commit()

async def get_all_settings() -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
            return {k: v for k, v in rows}

# --- Users ---
async def upsert_user(user_id: int, username: str | None, fullname: str):
    now = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO users(user_id, username, fullname, joined_at, last_seen, is_verified) VALUES(?, ?, ?, ?, ?, 0) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, fullname=excluded.fullname, last_seen=?",
            (user_id, username, fullname, now, now, now),
        )
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def set_verified(user_id: int, verified: bool = True):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET is_verified=?, verified_at=? WHERE user_id=?", (1 if verified else 0, int(time.time()) if verified else None, user_id))
        await db.commit()

async def ban_user(user_id: int, ban: bool = True):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if ban else 0, user_id))
        await db.commit()

async def add_warning(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET warnings = warnings + 1 WHERE user_id=?", (user_id,))
        await db.commit()
        async with db.execute("SELECT warnings FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def reset_warnings(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET warnings=0 WHERE user_id=?", (user_id,))
        await db.commit()

async def count_users(where: str = "") -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        q = f"SELECT COUNT(*) FROM users {where}"
        async with db.execute(q) as cur:
            return (await cur.fetchone())[0]

async def list_users(limit=20, offset=0):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, username, fullname, downloads, is_banned FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset)) as cur:
            return await cur.fetchall()

async def count_verified_users() -> int:
    return await count_users("WHERE is_verified=1")

# --- Captcha ---
async def set_captcha(user_id: int, question: str, answer: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO captcha_state(user_id, question, answer, attempts, created_at) VALUES(?, ?, ?, 0, ?)", (user_id, question, answer, int(time.time())))
        await db.commit()

async def get_captcha(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT question, answer, attempts, created_at FROM captcha_state WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def inc_captcha_attempt(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE captcha_state SET attempts = attempts + 1 WHERE user_id=?", (user_id,))
        await db.commit()

async def clear_captcha(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM captcha_state WHERE user_id=?", (user_id,))
        await db.commit()

# --- Channels ---
async def add_channel(username: str, invite_link: str = "", title: str = ""):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO channels(username, invite_link, title, created_at) VALUES(?, ?, ?, ?)", (username.strip(), invite_link.strip(), title.strip(), int(time.time())))
        await db.commit()

async def remove_channel(cid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id=?", (cid,))
        await db.commit()

async def toggle_channel(cid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE channels SET is_active = 1 - is_active WHERE id=?", (cid,))
        await db.commit()

async def list_channels(active_only=False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        q = "SELECT id, username, title, invite_link, is_active FROM channels"
        if active_only:
            q += " WHERE is_active=1"
        q += " ORDER BY id"
        async with db.execute(q) as cur:
            return await cur.fetchall()

# --- Ads ---
async def add_ad(text: str, photo_file_id: str | None, btn_text: str | None, btn_url: str | None, show_every: int = 3):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO ads(text, photo_file_id, button_text, button_url, show_every, created_at) VALUES(?, ?, ?, ?, ?, ?)", (text, photo_file_id, btn_text, btn_url, show_every, int(time.time())))
        await db.commit()

async def list_ads():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT id, text, photo_file_id, button_text, button_url, is_active, show_every FROM ads ORDER BY id DESC") as cur:
            return await cur.fetchall()

async def toggle_ad(aid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE ads SET is_active = 1 - is_active WHERE id=?", (aid,))
        await db.commit()

async def remove_ad(aid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM ads WHERE id=?", (aid,))
        await db.commit()

async def get_active_ad_for_user(download_count: int):
    ads = await list_ads()
    active = [a for a in ads if a[5] == 1]
    if not active:
        return None
    for ad in active:
        if download_count > 0 and download_count % ad[6] == 0:
            return ad
    return None

# --- Stats ---
async def inc_stat(field: str = "requests"):
    today = time.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO stats(date, downloads, users_new, requests) VALUES(?, 0, 0, 0) ON CONFLICT(date) DO NOTHING", (today,))
        allowed = {"downloads", "users_new", "requests"}
        if field in allowed:
            await db.execute(f"UPDATE stats SET {field} = {field} + 1 WHERE date=?", (today,))
        await db.commit()

async def get_stats(days=7):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT date, downloads, users_new, requests FROM stats ORDER BY date DESC LIMIT ?", (days,)) as cur:
            return await cur.fetchall()

async def get_platform_stats(days=7):
    """Return platform breakdown for last N days."""
    cutoff = int(time.time()) - days * 86400
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT platform, COUNT(*) FROM downloads_log WHERE created_at > ? AND success=1 GROUP BY platform", (cutoff,)) as cur:
            return await cur.fetchall()

async def get_top_users(limit=5, days=7):
    cutoff = int(time.time()) - days * 86400
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, COUNT(*) as c FROM downloads_log WHERE created_at > ? GROUP BY user_id ORDER BY c DESC LIMIT ?", (cutoff, limit)) as cur:
            return await cur.fetchall()

async def log_download(user_id: int, platform: str, url: str, title: str = "", duration: int = 0, file_size: int = 0, success: int = 1, error: str = ""):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO downloads_log(user_id, platform, url, title, duration, file_size, success, error, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, platform, url, title[:500], duration, file_size, success, error[:500], int(time.time())))
        if success:
            await db.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id=?", (user_id,))
        await db.commit()
    await inc_stat("downloads" if success else "requests")

# --- Rate limit ---
async def check_rate_limit(user_id: int, max_per_hour: int) -> tuple[bool, int]:
    now = int(time.time())
    hour_ago = now - 3600
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM rate_limit WHERE ts < ?", (hour_ago,))
        async with db.execute("SELECT COUNT(*) FROM rate_limit WHERE user_id=?", (user_id,)) as cur:
            cnt = (await cur.fetchone())[0]
        if cnt >= max_per_hour:
            async with db.execute("SELECT MIN(ts) FROM rate_limit WHERE user_id=?", (user_id,)) as cur:
                oldest = (await cur.fetchone())[0]
            wait = 3600 - (now - oldest) if oldest else 3600
            await db.commit()
            return False, wait
        await db.execute("INSERT INTO rate_limit(user_id, ts) VALUES(?, ?)", (user_id, now))
        await db.commit()
        return True, 0

async def check_flood_per_min(user_id: int, max_per_min: int) -> bool:
    now = int(time.time())
    min_ago = now - 60
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM rate_limit WHERE user_id=? AND ts > ?", (user_id, min_ago)) as cur:
            cnt = (await cur.fetchone())[0]
            return cnt < max_per_min

# --- Pending downloads (for quality selection) ---
async def save_pending(token: str, user_id: int, url: str, platform: str, meta_json: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO pending_downloads(token, user_id, url, platform, meta_json, created_at) VALUES(?, ?, ?, ?, ?, ?)", (token, user_id, url, platform, meta_json, int(time.time())))
        await db.commit()

async def get_pending(token: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, url, platform, meta_json FROM pending_downloads WHERE token=?", (token,)) as cur:
            return await cur.fetchone()

async def delete_pending(token: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM pending_downloads WHERE token=?", (token,))
        await db.commit()

async def cleanup_pending():
    cutoff = int(time.time()) - 3600
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM pending_downloads WHERE created_at < ?", (cutoff,))
        await db.commit()

# --- Auto delete queue ---
async def queue_auto_delete(chat_id: int, message_id: int, hours: float):
    if hours <= 0:
        return
    delete_at = int(time.time()) + int(hours * 3600)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO auto_delete_queue(chat_id, message_id, delete_at) VALUES(?, ?, ?)", (chat_id, message_id, delete_at))
        await db.commit()

async def get_due_deletes(limit=50):
    now = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT id, chat_id, message_id FROM auto_delete_queue WHERE delete_at <= ? LIMIT ?", (now, limit)) as cur:
            return await cur.fetchall()

async def remove_delete_entry(eid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM auto_delete_queue WHERE id=?", (eid,))
        await db.commit()
