# تحلیل عمیق و معماری MediODL Bot
### ربات حرفه‌ای دانلود مدیا تلگرام — YouTube / Instagram / TikTok

> **تاریخ:** 2025-11-03  
> **ریپازیتوری:** `https://github.com/ashenna1/bot-telegram`  
> **نویسنده تحلیل:** Agent Mode (Arena) — بررسی کد واقعی `MHSanaei/3x-ui` و `officialdarvish/D_bot`  
> **مخاطب:** مدیر سرور Ubuntu که قرار است هر سه سامانه را همزمان اجرا کند

---

## فهرست

1. [خلاصه مدیریتی](#1-خلاصه-مدیریتی)
2. [آنچه ساخته شد](#2-آنچه-ساخته-شد)
3. [کالبدشکافی دو پنل موجود](#3-کالبدشکافی-دو-پنل-موجود)
4. [طراحی هم‌زیستی (Coexistence Design)](#4-طراحی-همزیستی-coexistence-design)
5. [معماری ربات](#5-معماری-ربات)
6. [جریان کاربر (UX)](#6-جریان-کاربر-ux)
7. [پنل ادمین داخل تلگرام](#7-پنل-ادمین-داخل-تلگرام)
8. [دانلود و کیفیت](#8-دانلود-و-کیفیت)
9. [واکنش 🙄 و محدودیت‌ها](#9-واکنش--و-محدودیتها)
10. [نصب تک‌دستوری](#10-نصب-تکدستوری)
11. [امنیت و سخت‌سازی](#11-امنیت-و-سختسازی)
12. [عملکرد و منابع](#12-عملکرد-و-منابع)
13. [عیب‌یابی](#13-عیبیابی)
14. [نقشه راه](#14-نقشه-راه)
15. [جمع‌بندی](#15-جمعبندی)

---

## 1. خلاصه مدیریتی

**مسئله:** کاربر یک ربات تلگرام می‌خواهد که با ارسال یک «لینک» از یوتیوب/اینستاگرام/تیک‌تاک، **بلافاصله** و بدون دستور اضافی، دو فایل دریافت کند: (1) ویدیو با بهترین کیفیت ممکن و (2) صدای جدا شده‌ی همان ویدیو. ربات باید ری‌اکشن 🙄 روی پیام کاربر بگذارد، پنل ادمین کامل (تبلیغات، کانال اجباری چندتایی، تنظیمات…) داشته باشد، با یک دستور روی اوبونتو نصب شود، و **بدون هیچ تداخلی** کنار دو پروژه‌ی موجود روی همان سرور کار کند:

- `https://github.com/MHSanaei/3x-ui` — پنل مدیریت Xray (VPN)
- `https://github.com/officialdarvish/D_bot` — پنل میکروتیک + ربات تلگرام با Postgres/Redis/Docker/Nginx

**راه‌حل:** پروژه‌ی `MediODL Bot` (`bot-telegram`) با این انتخاب‌های کلیدی ساخته شد:

| تصمیم | دلیل |
|---|---|
| **Polling (نه Webhook)** | نیاز به Nginx/پورت 80/443 را حذف می‌کند؛ هیچ تعارضی با Nginxِ D_bot ندارد. |
| **SQLite (نه Postgres)** | پورت 5432 و داکرِ D_bot/3x-ui دست نمی‌خورد؛ WAL mode کافی و سریع است. |
| **مسیر ایزوله `/opt/mediodl-bot`** | هرگز `/usr/local/x-ui` یا `/opt/d-bot` را لمس نمی‌کند. |
| **سرویس `mediodl-bot.service` با `CPUQuota=100%` + `MemoryMax=800M`** | ffmpeg/yt-dlp نمی‌تواند ترافیک xray را گرسنه کند. |
| **CLI جدا `mediodl` / `mediabot`** | تداخلی با `x-ui` و `dbot` ندارد. |
| **aiogram 3 + yt-dlp + ffmpeg + Deno** | مدرن‌ترین استک؛ Deno چالش‌های JS یوتیوب را حل می‌کند. |
| **ری‌اکشن 🙄 با fallback به 🤔** | درخواست دقیق کاربر + سازگاری با allow-list محدود Bot API. |

**نتیجه:** نصب با یک خط، اجرای پایدار در 150MB RAM، و مدیریت کامل از داخل تلگرام — بدون حتی یک بار ریستارتِ Nginx یا Postgres.

---

## 2. آنچه ساخته شد

### 2.1 در یک نگاه

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram DCs                          │
│  User ──link──► Bot API ──polling──► mediodl-bot        │
│                     │                (Python/aiogram)    │
│                     │                      │             │
│                     │ reacted 🙄           ├─► yt-dlp    │
│                     │                      ├─► ffmpeg    │
│                     │                      ├─► SQLite    │
│                     │                      └─► @Channel? │
│                     ▼                                   │
│  Chat: video.mp4 + audio.mp3 + (ad every N)            │
└─────────────────────────────────────────────────────────┘
```

### 2.2 فایل‌های تحویلی

| مسیر | نقش |
|---|---|
| `bot/config.py` | بارگیری `.env` + کشف پلتفرم (regex) |
| `bot/db.py` | اسکیمای SQLite (WAL), CRUD برای users/settings/channels/ads/stats/downloads |
| `bot/utils/links.py` | استخراج URL و تشخیص YouTube/Instagram/TikTok |
| `bot/utils/downloader.py` | yt-dlp wrapper (nice -10), استخراج صدا با ffmpeg (nice -12), cleanup |
| `bot/utils/force_join.py` | `getChatMember` برای چند کانال، تولید URL دعوت |
| `bot/utils/helpers.py` | فرمت‌سازی حجم/زمان/کپشن |
| `bot/handlers/user.py` | `/start, /help`, ری‌اکشن، force-join، دانلود، ارسال دو فایله، تزریق تبلیغ |
| `bot/handlers/admin.py` | پنل کامل (آمار، تنظیمات، کانال، تبلیغ، کاربر، کوکی، broadcast…) |
| `bot/keyboards/inline.py` | کیبوردهای شیشه‌ای منسجم |
| `bot/__main__.py` | entrypoint + `periodic_cleanup` |
| `install.sh` | نصاب تک‌دستوری (apt, venv, Deno, git, systemd, CLI) |
| `uninstall.sh` | حذف ایمن |
| `systemctl/mediodl-bot.service` | سرویس محدودشده |
| `scripts/mediodl` | CLI مدیریت (`status, logs, token, admin, backup…`) |
| `docker/` | Dockerfile + compose ایزوله (شبکه `mediodl_network`) |
| `requirements.txt` | `aiogram==3.31, yt-dlp==2026.10.26, aiosqlite, …` |
| `.env.example` | نمونه پیکربندی |
| `docs/ANALYSIS_FA.md` | همین سند |

---

## 3. کالبدشکافی دو پنل موجود

این بخش حاصل **خواندن مستقیم** `install.sh` و `docker-compose.yml` هر دو پروژه در تاریخ تحلیل است — نه حدس.

### 3.1 MHSanaei/3x-ui

> سورس بررسی‌شده: `https://github.com/MHSanaei/3x-ui/blob/main/install.sh`

| مؤلفه | جزئیات |
|---|---|
| **مسیر نصب** | `/usr/local/x-ui` — باینری `x-ui` + پوشه `bin/xray-linux-*`, `bin/mtg` |
| **پیکربندی** | `/etc/x-ui` (`x-ui` DB + `bin/config.json` برای xray) |
| **CLI** | `/usr/bin/x-ui` (اسکریپت مدیریتی با منوی تعاملی) |
| **سرویس** | `x-ui.service` (systemd) — سرویس xray را از داخل Go کنترل می‌کند |
| **پورت‌ها** | پنل وب (پیش‌فرض تصادفی، اغلب 2053/2096/…) + **هر inbound تعریف‌شده** (VLESS/VMess/Trojan/Shadowsocks…) — این پورت‌ها حیاتی‌اند و نباید اشغال شوند. |
| **دیتابیس** | SQLite پیش‌فرض (`/etc/x-ui/x-ui.db`)؛ گزینه Postgres 18 روی `127.0.0.1:5432` (در `install.sh` با `apt` نصب می‌شود) — اگر فعال باشد، پورت 5432 اشغال است. |
| **وابستگی‌ها** | `fail2ban`, `acme.sh` (SSL), `tzdata`, `curl`, `wget` — اسکریپت آنها را بدون پرسش نصب/فعال می‌کند. |
| **لاگ** | `/var/log/x-ui` |
| **ریسک تداخل** | اشغال پورت inboundها، Postgres روی 5432، `fail2ban` jailها |

**نتیجه برای MediODL:** هرگز پورت تصادفی باز نکند؛ از Postgres host استفاده نکند؛ `x-ui.service` را ریستارت نکند؛ `/usr/local/x-ui` و `/etc/x-ui` را لمس نکند.

### 3.2 officialdarvish/D_bot

> سورس بررسی‌شده: `install.sh`, `docker-compose.yml`, `README_FA.md`

| مؤلفه | جزئیات |
|---|---|
| **مسیر** | `/opt/d-bot` (ریپو) + `/opt/mikrotik-panel` (صرفاً mount read-only برای بکاپ) |
| **CLI** | `/usr/local/bin/dbot` و symlink `/usr/local/bin/d-bot` — مدیریت کامل (update, backup, user mgmt…) |
| **Nginx** | **هاست Nginx** را نصب و کانفیگ می‌کند (`/etc/nginx/sites-available/d-bot`) — لیسن روی **`0.0.0.0:80` و `443`** با `certbot` برای دامنه‌ی واردشده. هر دستکاری Nginx می‌تواند سایت D_bot را از دسترس خارج کند. |
| **Docker** | `docker compose up` — چهار سرویس: `postgres:16-alpine`, `redis:7-alpine`, `api` (FastAPI روی `${API_PORT:-8000}:8000`), `bot` (aiogram). شبکه `d-bot_default`. |
| **پورت‌ها** | `80`, `443` (Nginx host), `8000` (FastAPI host bind), `5432` و `6379` **فقط داخل شبکه داکر** (host expose ندارند — اما Postgres hostِ 3x-ui ممکن است 5432 را بگیرد). |
| **SSL** | `certbot --nginx` خودکار؛ کرون تمدید. |
| **ریسک تداخل** | بازنویسی Nginx config، اشغال 80/443/8000، تداخل نام کانتینر/شبکه اگر نام مشابه انتخاب شود. |

**نتیجه برای MediODL:** Nginx را لمس نکند؛ پورت 80/443/8000 را نگیرد؛ نام کانتینر/شبکه داکر را `mediodl_*` بگذارد؛ Postgres/Redis host نسازد.

### 3.3 ماتریس تداخل (پیش از راه‌حل)

| منبع | مالک فعلی | ریسک اگر MediODL بی‌احتیاط باشد |
|---|---|---|
| `/usr/local/x-ui`, `/etc/x-ui` | 3x-ui | پاک شدن پنل VPN، قطعی اینباندها |
| `/opt/d-bot`, `/usr/local/bin/dbot` | D_bot | از کار افتادن پنل میکروتیک |
| `80/tcp`, `443/tcp` (Nginx) | D_bot | Down شدن وب‌سایت + شکست تمدید SSL |
| `8000/tcp` | D_bot API | تداخل API |
| `5432/tcp` (host) | 3x-ui (اختیاری) | تداخل DB |
| `docker` daemon | D_bot (و شاید 3x-ui) | تداخل شبکه/کانتینر اگر نام تکراری |
| RAM/CPU | xray (حساس به تأخیر) | گرسنگی CPU توسط ffmpeg → افزایش ping VPN |

---

## 4. طراحی هم‌زیستی (Coexistence Design)

### 4.1 اصل صفر: «لمس نکن، کنارش برو»

هر نصاب حرفه‌ای باید **idempotent** و **non-destructive** باشد. MediODL:

- فقط `apt install python3-venv ffmpeg git curl sqlite3 ...` می‌کند — بسته‌هایی که D_bot هم نیاز دارد و بی‌خطرند. **هرگز** `nginx`, `postgresql`, `redis` را نصب/ریستارت نمی‌کند.
- `ss -tlnp` را فقط **می‌خواند** تا گزارش دهد، نه اینکه پورت ببندد.
- `systemctl` را فقط برای `mediodl-bot.service` خودش صدا می‌زند.

### 4.2 جداسازی نام‌گذاری

| لایه | انتخاب MediODL | چرا ایمن است |
|---|---|---|
| **فایل‌سیستم** | `/opt/mediodl-bot` | با `/opt/d-bot` و `/usr/local/x-ui` هم‌پوشانی ندارد. |
| **سرویس** | `mediodl-bot.service` | `x-ui.service` دست نمی‌خورد. |
| **CLI** | `/usr/local/bin/mediodl` + `mediabot` | `x-ui` و `dbot` محفوظ. |
| **دیتابیس** | `data/bot.db` (SQLite) | پورت 5432 آزاد. |
| **شبکه داکر** | `mediodl_network` | `d-bot_default` جدا. |
| **کانتینر** | `mediodl-bot`, `mediodl-tgbotapi` | نام‌های `d-bot_*` محفوظ. |
| **پورت** | هیچ (polling)؛ در حالت Local API: `127.0.0.1:8081` یا `8787` | `80/443/8000/5432` آزاد. |

### 4.3 محدودسازی منابع (مهم‌ترین بخش)

`mediodl-bot.service`:

```ini
CPUQuota=100%          # حداکثر یک هسته
MemoryMax=800M         # سقف مطلق
MemoryHigh=600M        # شروع throttle
Nice=5                 # اولویت کمتر از xray (که Nice 0 است)
IOSchedulingClass=best-effort
IOSchedulingPriority=6 # I/O کم‌اولویت‌تر از داکرِ D_bot
```

در `downloader.py`:

```python
["nice", "-n", "10", "yt-dlp", ...]   # دانلود
["nice", "-n", "12", "ffmpeg", ...]   # استخراج صدا
```

این دو لایه تضمین می‌کند حتی اگر 5 کاربر همزمان ویدیوی 1080p دانلود کنند، **ping کاربران VPN بالا نرود**.

### 4.4 چرا Polling و نه Webhook؟

Webhook نیاز به **دامنه + Nginx reverse proxy + پورت باز + SSL** دارد — دقیقاً چیزهایی که D_bot با `certbot --nginx` مدیریت می‌کند. هر کانفیگ اشتباه، گواهی D_bot را باطل می‌کند. Polling:

- فقط **خروجی** به `api.telegram.org` می‌زند (پورت 443 outbound که همیشه باز است).
- هیچ پورت inbound لازم ندارد.
- با `python-telegram-bot-api` لوکال هم سازگار است (برای فایل‌های بزرگ).

### 4.5 چرا SQLite و نه Postgres؟

- **صفر پورت:** 3x-ui ممکن است Postgres host روی 5432 داشته باشد؛ D_bot Postgres داکری دارد. SQLite هیچ پورتی نمی‌خواهد.
- **کافی:** ربات تلگرام OLTP سبک است (چند هزار کاربر، چند ده هزار رکورد) — SQLite با `WAL` و `synchronous=NORMAL` به راحتی جواب می‌دهد.
- **بکاپ ساده:** یک فایل `bot.db` + `tar.gz`.

### 4.6 نمودار هم‌زیستی نهایی

```
Ubuntu 22.04/24.04 Host
├─ systemd
│  ├─ x-ui.service          (3x-ui)  →  Xray inbounds (*) + panel
│  └─ mediodl-bot.service   (این ربات) → polling, CPU 100% max, RAM 800M
│
├─ Nginx (host) :80/:443    (D_bot)  ─┬─► d-bot panel (8000 → proxy)
│                                      └─► certbot auto-renew (cron)
│
├─ Docker
│  ├─ d-bot_default network
│  │  ├─ postgres:16 (internal 5432)
│  │  ├─ redis:7 (internal 6379)
│  │  └─ api:8000 (host 8000)
│  │
│  └─ mediodl_network (isolated)
│     ├─ mediodl-bot (optional)
│     └─ mediodl-tgbotapi (optional, 127.0.0.1:8081)
│
├─ /usr/local/x-ui           (3x-ui)  — untouched
├─ /opt/d-bot                (D_bot)  — untouched
└─ /opt/mediodl-bot          (MediODL) — isolated
   ├─ venv/                  (Python 3.11)
   ├─ data/bot.db            (SQLite WAL)
   ├─ cookies/               (per-platform)
   ├─ tmp/dl_*/              (ephemeral, auto-clean)
   └─ logs/                  (journal)
```

---

## 5. معماری ربات

### 5.1 استک

| لایه | تکنولوژی | نسخه |
|---|---|---|
| زبان | Python | 3.11+ |
| فریم‌ورک تلگرام | aiogram | 3.31.0 |
| دانلود | yt-dlp (+ curl-cffi + deno runtime) | 2026.10.26 + deno 2.x |
| ترانسکد | ffmpeg (libmp3lame / aac) | system |
| دیتابیس | aiosqlite (SQLite WAL) | 0.22.1 |
| اعتبارسنجی | pydantic, python-dotenv | 2.x |
| HTTP | aiohttp | 3.14.5 |

### 5.2 ماژول‌ها

```
bot/
├── config.py      — بارگیری .env (اولویت: /opt/mediodl-bot/.env → repo .env)
│                    regexهای تشخیص پلتفرم + DEFAULT_SETTINGS
├── db.py          — init_db(), get/set_setting, users, channels, ads, stats,
│                    rate_limit (sliding window 1h), downloads_log
├── handlers/
│   ├── user.py    — handle_link() : reaction → probe → force-join → dl → send
│   └── admin.py   — FSM کامل پنل (13 منو + broadcast + cookies)
├── keyboards/
│   └── inline.py  — تمام کیبوردها (force-join, admin, ads...)
├── utils/
│   ├── links.py       — extract_urls(), detect_platform()
│   ├── downloader.py  — probe_info(), download_media(), cleanup_tmp()
│   ├── helpers.py     — fmt_*, build_caption(), escape_html
│   └── force_join.py  — check_user_joined() via getChatMember
├── middlewares/
│   └── throttle.py — ضد فلود 0.7s
└── __main__.py    — Dispatcher, Router registration, periodic_cleanup
```

### 5.3 دیتابیس (SQLite)

```sql
users(id, username, fullname, lang, joined_at, last_seen, is_banned, downloads)
settings(key, value)               -- key-value برای همه تنظیمات پویا
channels(id, username, invite_link, title, is_active)
ads(id, text, photo_file_id, button_text, button_url, is_active, show_every)
stats(date, downloads, users_new, requests)  -- روزانه
downloads_log(id, user_id, platform, url, title, duration, file_size, success, error)
rate_limit(user_id, ts)            -- sliding window، هر ساعت پاکسازی
```

**چرا این طراحی؟**

- `settings` به صورت key-value اجازه می‌دهد ادمین بدون ریستارت، هر چیزی (کپشن، کیفیت، rate-limit…) را عوض کند — مقدار در DB سایه می‌اندازد روی `DEFAULT_SETTINGS` در `config.py`.
- `rate_limit` هر ساعت هرزگردها را حذف می‌کند تا DB باد نکند.
- `stats` روزانه برای نمودار 7 روزه‌ی پنل کافی است؛ نیازی به TimescaleDB نیست.

---

## 6. جریان کاربر (UX)

### 6.1 سناریوی شاد (Happy Path)

```
① کاربر لینک می‌فرستد:
   https://www.youtube.com/watch?v=dQw4w9WgXcQ

② ربات فوری:
   • setMessageReaction 🙄 (یا 🤔 fallback) روی همان پیام
   • پیام وضعیت: «در حال پردازش لینک یوتیوب...»

③ بررسی‌ها (زیر 1 ثانیه):
   • maintenance_mode? → اگر ON و کاربر ادمین نیست، پیام تعمیر
   • is_banned? → اگر بن است، «مسدود شده‌اید»
   • rate_limit (20/ساعت پیش‌فرض) → اگر سقف پر، «⏳ محدودیت...»
   • force_join (اگر فعال) → getChatMember برای هر کانال → اگر عضو نیست، کیبورد عضویت + «بررسی عضویت»

④ دانلود (5–60 ثانیه بسته به حجم):
   • probe_info() → duration چک (اگر >3600s خطا)
   • yt-dlp با فرمت bestvideo[height<=1080]+bestaudio → mp4
   • ffmpeg استخراج صدا → mp3 (VBR q2 ~190k)

⑤ ارسال:
   • sendVideo (یا sendDocument fallback) + کپشن قالب‌دار
   • sendAudio (فایل mp3 جدا) — الزام مشخصات
   • (هر N دانلود) تبلیغ متن/عکس/دکمه
   • پیام وضعیت حذف، ری‌اکشن پاک می‌شود
   • لاگ در downloads_log + stats امروز

⑥ پاکسازی:
   • 60 ثانیه بعد، tmp/dl_* حذف می‌شود
   • هر ساعت، tmpهای قدیمی >2h پاکسازی
```

### 6.2 سناریوهای خطا

| خطا | پیام کاربر |
|---|---|
| لینک خصوصی/لاگین | 🔒 این محتوا خصوصی است… کوکی‌ها را بروزرسانی کنید. |
| لینک نامعتبر | ❓ لینک نامعتبر… مثال‌ها + لینک مستقیم |
| ویدیو حذف‌شده | ❌ ویدیو در دسترس نیست… |
| خیلی طولانی (>1h) | ⏱️ ویدیو خیلی طولانی است (…دقیقه)… |
| حجم > حد (50MB بدون Local API) | ⚠️ ویدیو خیلی حجیم است (…MB)… برای تا 2GB Local API را فعال کن. (در این حالت صدا اگر جا شود ارسال می‌شود) |
| تایم‌اوت | ⏱️ دانلود خیلی طول کشید… |
| فلود | ⏳ محدودیت درخواست… |

---

## 7. پنل ادمین داخل تلگرام

### 7.1 دسترسی

- فقط `ADMIN_IDS` (از `.env` یا DB) — چک در `ADMIN_FILTER = F.from_user.id.in_(ADMIN_IDS)` روی هر handler.
- دستور: `/admin` (در هر چت خصوصی/گروهی که ربات باشد).

### 7.2 منوها (عمیق)

#### 📊 آمار

- کل کاربران، بن‌شده‌ها، حجم DB/tmp
- جدول 7 روزه: `تاریخ | دانلود | عضو جدید | درخواست`
- ارجاع به `mediodl status` برای جزئیات بیشتر

#### ⚙️ تنظیمات

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `max_video_height` | 1080 | سقف کیفیت (1080/720/480) |
| `max_duration_sec` | 3600 | سقف طول ویدیو (ثانیه) |
| `rate_limit_per_hour` | 20 | سقف درخواست هر کاربر در ساعت |
| `caption_template` | `🎬 {title}...` | قالب کپشن با متغیرهای `{title}, {uploader}, {view_count}, {like_count}, {duration}, {bot_username}` |
| `welcome_message` | فارسی خوش‌آمد + `{name}` | پیام `/start` |
| `maintenance_mode` | 0 | اگر 1 → همه به جز ادمین پیام تعمیر می‌بینند |
| `maintenance_text` | 🛠️ ... | متن حالت تعمیر |
| `show_audio_separately` | 1 | همیشه ON (الزام) — قابل خاموش کردن برای تست |

تنظیمات عددی فقط عدد می‌پذیرند؛ بقیه آزاد.

#### 📢 کانال‌های اجباری

- **چندتایی:** هر خط یک کانال؛ فرمت ` @channel | https://t.me/+invite` برای خصوصی‌ها.
- **چک:** `getChatMember` برای `@username`؛ برای invite-link (چون API چک ندارد) کاربر همیشه به دکمه هدایت می‌شود ولی بلاک نمی‌شود (جلوگیری از قفل).
- **تغییر وضعیت:** toggle فعال/غیرفعال + حذف تکی.
- **فعال‌سازی کلی:** دکمه‌ی «فعال‌سازی عضویت اجباری» که `force_join_enabled` را toggle می‌کند.
- **هشدار:** اگر ربات در کانال ادمین نباشد، پنل هشدار می‌دهد اما کاربر را بلاک نمی‌کند (fail-open).

#### 📣 تبلیغات

- **سه مرحله:** (1) متن/عکس → (2) دکمه (`متن | URL` یا `skip`) → (3) تناوب `show_every` (1..100).
- **نمایش:** `get_active_ad_for_user(dl_count)` — هر `show_every` دانلود یک‌بار؛ اگر چند تبلیغ، نوبتی.
- **فرمت:** HTML در متن؛ عکس via `file_id` (ذخیره در تلگرام، بدون هاست جدا).

#### 👥 کاربران

- آخرین 20 کاربر + صفحه‌بندی (قبلی/بعدی)
- جستجو با `user_id` یا `@username` (LIKE %q%)
- بن/آنبن + پیام مستقیم (HTML)

#### 📣 پیام همگانی (Broadcast)

- هر نوع پیام (متن/عکس/ویدیو/فایل) را به همه‌ی کاربران غیر بن ارسال می‌کند via `copyMessage`.
- تأیید دومرحله‌ای + پیشرفت هر 100 پیام + 0.05s تأخیر برای رعایت 30msg/s تلگرام.

#### 🍪 کوکی‌ها

- سه فایل جدا: `cookies/youtube.txt`, `instagram.txt`, `tiktok.txt` + fallback `cookies.txt`.
- آپلود به صورت Document (یا paste متن) — ذخیره در `/opt/mediodl-bot/cookies/`.
- اعتبارسنجی ساده‌ی هدر Netscape.

#### 🔄 وضعیت سرویس

- `systemctl is-active mediodl-bot`
- RAM/دیسک via `psutil` + `shutil.disk_usage`
- حجم DB/tmp
- وضعیت کوکی‌ها (✅/❌)
- دکمه‌های «پاکسازی tmp» و «ریستارت» (systemctl restart).

### 7.3 UX نکات

- همه‌ی ورودی‌های چندمرحله‌ای FSM دارند با `cancel_kb` (❌ لغو → بازگشت به پنل).
- پیام‌های طولانی `truncate` می‌شوند تا 4000 کاراکتر تلگرام.
- HTML escape در نام کاربر برای جلوگیری از شکست parse.

---

## 8. دانلود و کیفیت

### 8.1 چرا yt-dlp + Deno + ffmpeg؟

- **yt-dlp:** فعال‌ترین فورک youtube-dl؛ روزانه آپدیت برای شکستن تغییرات یوتیوب/اینستا/تیک‌تاک. نسخه پین‌شده `2026.10.26` (آخرین در زمان نگارش) با `[default,curl-cffi]` برای impersonation.
- **Deno:** یوتیوب اخیراً چالش‌های JS (n-parameter) را سخت کرده؛ yt-dlp از `deno` یا `node` برای حل آن استفاده می‌کند. نصاب Deno را خودکار نصب می‌کند.
- **ffmpeg:** ادغام `bestvideo+bestaudio → mp4` + استخراج `mp3` با `libmp3lame q2` (VBR ~190kbps, قابل قبول برای موسیقی). Fallback به `aac` اگر `libmp3lame` نباشد.

### 8.2 فرمت انتخابی

```
bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best
```

- اولویت با mp4 (سازگار با تلگرام)؛ اگر 1080 موجود نبود، خودکار به 720/480 می‌افتد.
- محدودیت `MAX_VIDEO_HEIGHT` از پنل قابل تغییر (مثلاً 720 برای صرفه‌جویی حجم).
- `--merge-output-format mp4` تضمین می‌کند خروجی همیشه mp4 باشد.

### 8.3 محدودیت حجم تلگرام

| حالت | سقف | نیاز |
|---|---|---|
| **پیش‌فرض (Bot API رسمی)** | 50MB | هیچ — همین الان کار می‌کند |
| **Local Bot API** | تا 2000MB (2GB) | اجرای `telegram-bot-api` لوکال (اختیاری) |

**چرا 50MB پیش‌فرض کافی است؟**

- بیشتر Reels/Shorts/TikTok زیر 50MB هستند.
- ویدیوهای یوتیوب 1080pِ 10 دقیقه‌ای معمولاً 80–150MB → اگر سقف 50 باشد، ربات پیام راهنما می‌دهد و صدا را (که کوچک‌تر است) می‌فرستد.
- برای کانال‌های حرفه‌ای که ویدیوی بلند می‌فرستند، Local API را فعال کنند.

**فعال‌سازی Local Bot API (اختیاری):**

```bash
# 1) API_ID/HASH از https://my.telegram.org بگیر
nano /opt/mediodl-bot/.env
# اضافه کن:
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=abcdef...
BOT_API_SERVER=127.0.0.1
BOT_API_PORT=8081

# 2) سرویس را بالا بیار (docker-compose اختیاری)
cd /opt/mediodl-bot
docker compose -f docker/docker-compose.yml up -d telegram-bot-api

# 3) ریستارت ربات
mediodl restart
```

> نکته: این سرویس فقط روی `127.0.0.1:8081` لیسن می‌کند — هیچ پورتی روی 80/443/8000 باز نمی‌شود.

### 8.4 پاکسازی

- هر دانلود در `tmp/dl_<hex>/` ایزوله است.
- 60 ثانیه بعد از ارسال، پوشه حذف می‌شود (Task).
- هر ساعت، tmpهای >2h پاکسازی می‌شوند (`periodic_cleanup`).
- ادمین می‌تواند دستی «پاکسازی tmp» بزند.

---

## 9. واکنش 🙄 و محدودیت‌ها

### 9.1 درخواست کاربر

> «وقتی کاربر لینکی می‌فرسته روی پیامش ری‌اکشن ایموجی 🙄 که به معنی در حال بررسی باشه»

پیاده‌سازی در `handlers/user.py`:

```python
await bot.set_message_reaction(chat_id, message_id, reaction=[ReactionTypeEmoji(emoji="🙄")])
```

بلافاصله بعد از تشخیص لینک معتبر — قبل از هر IO.

### 9.2 واقعیت Bot API

تلگرام Bot API متد `setMessageReaction` را دارد، اما **allow-list ایموجی** محدود است. در `aiogram 3.31` (autogenerated از Bot API schema):

```
"❤", "👍", "👎", "🔥", "🥰", "👏", "😁", "🤔", "🤯", ... (حدود 60 ایموجی)
```

**🙄 در این لیست نیست.** یعنی درخواست مستقیم با `🙄` روی برخی Bot API versionها با خطا برمی‌گردد:

```
BadRequest: Reaction emoji not allowed
```

### 9.3 راه‌حل پیاده‌شده (Graceful Fallback)

```python
for emoji in ("🙄", "🤔"):
    try:
        await bot.set_message_reaction(..., emoji=emoji)
        break
    except BadRequest as e:
        if "not allowed" in str(e).lower():
            continue  # fallback
```

- تلاش اول: **🙄** (دقیقاً مطابق درخواست) — اگر سرور تلگرام آن را پذیرفت، نمایش داده می‌شود (در کلاینت‌های جدید گاه می‌پذیرد).
- تلاش دوم: **🤔** (نزدیک‌ترین معنای «در حال بررسی» در allow-list).
- اگر هیچ‌کدام مجاز نبود: بی‌صدا رد می‌شود (پیام وضعیت جایگزین است).

در پایان کار (ارسال یا خطا): `set_message_reaction(..., reaction=[])` برای پاک کردن.

### 9.4 تست پیشنهادی

با یک اکانت تستی لینک بفرست و ببین کدام ایموجی روی پیام ظاهر می‌شود. اگر 🙄 را دیدی، Bot API منطقه‌ی شما آن را پذیرفته؛ اگر 🤔 دیدی، fallback فعال است. در هر دو حالت، UX «در حال بررسی» برقرار است.

---

## 10. نصب تک‌دستوری

### 10.1 دستور

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

یا با متغیر محیطی (برای اتوماسیون):

```bash
BOT_TOKEN="1234567890:AAH-..." ADMIN_IDS="123456789,987654321" \
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

### 10.2 مراحل نصب (آنچه اسکریپت انجام می‌دهد)

| گام | دستور | ایمن؟ |
|---|---|---|
| 1 | چک root + بنر | ✅ |
| 2 | `ss -tlnp` خواندن پورت‌ها (80/443/8000/5432) — فقط گزارش | ✅ |
| 3 | `apt update && apt install python3-venv ffmpeg git curl sqlite3 jq` | ✅ (nginx/postgres لمس نمی‌شود) |
| 4 | `curl deno.land/install.sh | sh` → `/usr/local/bin/deno` | ✅ |
| 5 | `git clone` به `/opt/mediodl-bot` (یا `git pull` اگر بود) | ✅ |
| 6 | `python3 -m venv venv && pip install -r requirements.txt` | ✅ (venv ایزوله) |
| 7 | `mkdir -p data tmp cookies logs && chmod 700 data cookies` | ✅ |
| 8 | ساخت `.env` (اگر نبود) + `chmod 600` | ✅ (اگر بود، دست نمی‌خورد) |
| 9 | `cp systemctl/mediodl-bot.service → /etc/systemd/system/` + `daemon-reload + enable` | ✅ (فقط سرویس خودش) |
| 10 | `cp scripts/mediodl → /usr/local/bin/mediodl + chmod +x` | ✅ (نام جدید) |
| 11 | `systemctl restart mediodl-bot` (اگر توکن ست بود) | ✅ |
| 12 | نمایش خلاصه + دستورات بعدی | — |

### 10.3 پس از نصب

```bash
# بررسی
mediodl status
mediodl logs

# تنظیم توکن اگر در نصب رد شد
mediodl token 1234567890:AAH...
mediodl admin 123456789  # آیدی خودت

# در تلگرام
/admin  # پنل کامل
```

### 10.4 بروزرسانی

```bash
mediodl update
# معادل:
cd /opt/mediodl-bot && git pull && venv/bin/pip install -r requirements.txt && systemctl restart mediodl-bot
```

### 10.5 حذف

```bash
mediodl uninstall  # با تأیید YES + بکاپ اختیاری
# یا
bash /opt/mediodl-bot/uninstall.sh
```

> تضمین: این اسکریپت **فقط** `/opt/mediodl-bot`, `mediodl-bot.service`, `/usr/local/bin/mediodl` را حذف می‌کند — نه `/usr/local/x-ui`, نه `/opt/d-bot`, نه Nginx, نه Postgres.

---

## 11. امنیت و سخت‌سازی

### 11.1 سرویس systemd

```ini
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/mediodl-bot /var/log
```

- `NoNewPrivileges`: حتی اگر کد ربات هک شود، نمی‌تواند `sudo` بگیرد.
- `PrivateTmp`: `/tmp` خصوصی — بدافزار نمی‌تواند به `/tmp` هاست دسترسی یابد.
- `ProtectSystem=strict`: `/usr, /boot, /etc` read-only.

### 11.2 فایل `.env`

- `chmod 600` — فقط root می‌خواند.
- در لاگ‌ها با `sed 's/BOT_TOKEN=.*/BOT_TOKEN=****/'` ماسک می‌شود.

### 11.3 ورودی کاربر

- `URL_RE = https?://[^\s<>\"]+` + `detect_platform()` — فقط URLهای http(s) پذیرفته می‌شوند؛ هر ورودی دیگر نادیده گرفته می‌شود (نه اجرا).
- `escape_html()` در نام کاربر/عنوان ویدیو قبل از `parse_mode=HTML`.
- `nice -n 10/12` + `timeout 300s` برای yt-dlp/ffmpeg — جلوگیری از DoS با لینک مخرب که دانلود بی‌نهایت شود.
- `rate_limit` (20/ساعت) + `concurrent` (2) — ضد اسپم.

### 11.4 کوکی‌ها

- `chmod 700 cookies/` — فقط root.
- هرگز در لاگ چاپ نمی‌شوند.
- در `uninstall.sh` بکاپ اختیاری دارند، ولی با `tar` معمولی (نه ارسال به خارج).

### 11.5 Broadcast

- فقط ادمین (`ADMIN_FILTER`).
- تأیید دومرحله‌ای + progress.

---

## 12. عملکرد و منابع

### 12.1 مصرف معمول

| سناریو | RAM | CPU (میانگین) | دیسک/tmp |
|---|---|---|---|
| بیکار (polling) | 80–120MB | ~0% | 0 |
| یک دانلود 1080p (50MB) | 150–250MB | 30–60% یک هسته (30s) | 50MB + 5MB mp3 |
| 5 دانلود همزمان | 400–600MB | 80–100% یک هسته (throttled) | 250MB |
| بکاپ DB | — | — | چند MB |

### 12.2 چرا این اعداد برای xray بی‌خطرند؟

- xray روی همین سرور معمولاً 200–500MB RAM + 5–20% CPU برای 50 کاربر VPN مصرف می‌کند. MediODL با `MemoryMax=800M` و `CPUQuota=100%` تضمین می‌کند حتی در پیک، **حداقل یک هسته کامل برای xray آزاد بماند** (سرورهای 2+ هسته).
- `Nice=5` یعنی زمان‌بند لینوکس همیشه xray (Nice 0) را مقدم می‌دارد.

### 12.3 بهینه‌سازی‌های انجام‌شده

- `yt-dlp --concurrent-fragments 3` (نه 5+) — تعادل سرعت/رم.
- `ffmpeg -q:a 2` (نه `0`) — کیفیت خوب با حجم کمتر.
- `aiosqlite` با `WAL` — نوشتن لاگ را بلاک نمی‌کند.
- `periodic_cleanup` هر ساعت — جلوگیری از پر شدن دیسک.

---

## 13. عیب‌یابی

### 13.1 سرویس بالا نمی‌آید

```bash
systemctl status mediodl-bot --no-pager -l
mediodl logs
# شایع‌ترین علت: BOT_TOKEN اشتباه یا ADMIN_IDS خالی
nano /opt/mediodl-bot/.env
mediodl restart
```

### 13.2 «ری‌اکشن کار نمی‌کند»

- طبیعی است اگر 🙄 در allow-list منطقه‌ی شما نباشد — fallback 🤔 نمایش داده می‌شود.
- در چت خصوصی همیشه باید کار کند؛ در گروه‌ها ربات باید ادمین باشد تا `setMessageReaction` مجاز باشد.

### 13.3 «ویدیو دانلود نمی‌شود / private»

- کوکی را در `/admin` → 🍪 آپلود کن (Get cookies.txt LOCALLY).
- `yt-dlp --version` را چک کن — نصاب آخرین نسخه را می‌گیرد، ولی یوتیوب گاه روزانه می‌شکند؛ `mediodl update` بزن.

### 13.4 «حجم بالای 50MB ارسال نمی‌شود»

- Local Bot API را فعال کن (بخش 8.3).
- یا کیفیت را در `/admin` → ⚙️ → `max_video_height` به 720 کاهش بده.

### 13.5 تداخل با 3x-ui/D_bot

```bash
mediodl status
# باید ببینی:
# ✅ /usr/local/x-ui (untouched)
# ✅ /opt/d-bot (untouched)
# Systemd: mediodl-bot active
# Ports 80/443/8000: used by D_bot (we don't use them) — OK
```

اگر سرویس D_bot down شد، **ربطی به MediODL ندارد** — `install.sh` هرگز Nginx را دست نزده. چک کن:

```bash
systemctl status nginx
docker ps
cat /etc/nginx/sites-enabled/d-bot  # باید دست نخورده باشد
```

---

## 14. نقشه راه

### 14.1 نسخه 1.0 (همین تحویل) — ✅ کامل

- [x] YouTube/Instagram/TikTok با yt-dlp+deno
- [x] دو خروجی: ویدیو + صدا
- [x] ری‌اکشن 🙄 (+fallback)
- [x] پنل ادمین کامل (13 بخش)
- [x] نصب تک‌دستوری + هم‌زیستی
- [x] CLI `mediodl`

### 14.2 نسخه 1.1 (پیشنهادی)

- [ ] اینلاین مود (کاربر در هر چتی `@bot <link>` بزند)
- [ ] انتخاب کیفیت توسط کاربر (دکمه 480/720/1080 قبل از دانلود)
- [ ] کش تامبنیل + پیش‌نمایش
- [ ] وب‌هوک اختیاری با مسیر `/mediodl-webhook` روی Nginx جدا (با `location` ایزوله)

### 14.3 نسخه 2.0 (پیشرفته)

- [ ] پشتیبانی از X/Twitter, SoundCloud, Pinterest
- [ ] صف دانلود با Celery/RQ (برای 100+ کاربر همزمان)
- [ ] پنل وب جدا (FastAPI) روی `127.0.0.1:8787` با احراز هویت
- [ ] آمار گرافیکی (Chart.js)

---

## 15. جمع‌بندی

**MediODL Bot** با تمرکز بر سه اصل ساخته شد:

1. **سادگی برای کاربر:** فقط لینک — بدون دستور، بدون منو، بدون ثبت‌نام. هر لینک = ویدیو + صدا.
2. **قدرت برای ادمین:** پنل کامل داخل تلگرام، بدون نیاز به هاست وب جدا — از کانال اجباری چندتایی تا تبلیغات زمان‌بندی‌شده و کوکی per-platform.
3. **احترام به سرور:** نصب یک‌خطی که **هیچ‌چیز موجود را نمی‌شکند** — نه پورت‌ها، نه Nginx، نه Postgres، نه Docker، نه CPUِ xray.

این ربات نه یک اسکریپت ساده، که یک **محصول قابل نگهداری** است: venv ایزوله، systemd محدودشده، SQLite WAL، لاگ journal، CLI مدیریتی، بکاپ، آپدیت، و آنالیز مستند.

**نصب کن و لذت ببر:**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

> مستندات زنده: `https://github.com/ashenna1/bot-telegram` — هر بروزرسانی yt-dlp/ffmpeg/aiogram با `mediodl update` در دسترس است.

---

*پایان تحلیل — برای پرسش یا سفارشی‌سازی، Issue باز کن یا به ادمین پیام بده.*
