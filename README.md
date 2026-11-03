# MediGo (MediODL) Bot — Professional Telegram Media Downloader

> **فارسی** | [English](#english) | [تحلیل هم‌زیستی](docs/ANALYSIS_FA.md)

ربات تلگرام **حرفه‌ای، فان و پرسرعت** برای دانلود از **9 پلتفرم** — هر لینک = **ویدیو باکیفیت + صدای جدا** 🎬🎧

ساخته شده با `Aiogram 3 + yt-dlp + Deno + ffmpeg` — با **حالت دوستانه، کپچا باحال، و پنل ادمین کامل**.

## ✨ ویژگی‌ها

| قابلیت | توضیح |
|---|---|
| 🔴 **YouTube** | ویدیو، Shorts، Music |
| 📸 **Instagram** | پست، Reels، Stories |
| 🎵 **TikTok** | ویدیو + vm/vt |
| 📌 **Pinterest** | پین + pin.it |
| 🐦 **Twitter/X** | توییت ویدیویی + t.co |
| 👥 **Facebook** | ویدیو، Reels، fb.watch |
| 🎧 **SoundCloud** | صوت باکیفیت |
| 💚 **Spotify** | جستجوی خودکار یوتیوب (بهترین جایگزین) |
| 🧵 **Threads** | پست ویدیویی |
| 🎬 **دو خروجی** | ویدیو (mp4) + صدا (mp3) جداگانه |
| 🎚️ **انتخاب کیفیت** | 480/720/1080/فقط صدا — کاربر انتخاب می‌کند |
| 🙄 **ری‌اکشن** | روی لینک فوراً 🙄 (fallback 🤔) |
| 🛡️ **کپچا باحال** | ایموجی 🍎 یا ریاضی — فقط بار اول |
| 🚦 **ضداسپم** | محدودیت دقیقه‌ای/ساعتی + بن خودکار |
| 🔒 **عضویت اجباری** | چند کانال با `getChatMember` |
| 📣 **تبلیغات** | متن+عکس+دکمه، هر N دانلود |
| 📢 **کانال لاگ** | عضو جدید/دانلود/خطا → ادمین یا کانال |
| 🗑️ **حذف خودکار** | ویدیو بعد X ساعت پاک می‌شود |
| 📊 **آمار پیشرفته** | 7/30 روزه، تفکیک پلتفرم، تاپ کاربران |
| 😎 **حالت فان** | کامپلیمنت، فکت، جوک — دوستانه |
| 🍪 **کوکی** | 9 پلتفرم جدا + generic |
| 👑 **پنل ادمین** | کامل داخل تلگرام |
| 🚀 **نصب تک‌دستوری** | هم‌زیستی تضمین‌شده با 3x-ui و D_bot |

### 👑 پنل ادمین (`/admin`)

```
📊 آمار پیشرفته (7 روزه، تفکیک پلتفرم، تاپ 5)
⚙️ تنظیمات (کیفیت، کپشن، خوش‌آمد، محدودیت، انتخاب کیفیت)
📢 کانال اجباری (چندتایی)
📣 تبلیغات (عکس+دکمه، تناوب)
👥 کاربران (لیست، جستجو، بن/آنبن، DM)
📥 لاگ دانلودها
🍪 کوکی (9 پلتفرم)
🔄 وضعیت سرویس
📣 پیام همگانی
🧹 پاکسازی
🛡️ کپچا & ضداسپم (روشن/خاموش، حالت emoji/math/both، فان)
📢 کانال لاگ (به ادمین یا کانال، گزارش روزانه 09:00)
🗑️ حذف خودکار (1h/6h/24h/خاموش)
🔄 بروزرسانی (داخل تلگرام یا mediodl update)
😎 حالت فان
```

---

## 🚀 نصب تک‌دستوری (Ubuntu 20.04/22.04/24.04)

> سازگار با `MHSanaei/3x-ui` و `officialdarvish/D_bot` — هیچ پورت/سرویسی را بازنویسی نمی‌کند.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

یا:
```bash
BOT_TOKEN="1234:AAH..." ADMIN_IDS="123..." bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

### بعد از نصب
```bash
mediodl status
mediodl logs -f
mediodl token <TOKEN>
mediodl admin <ID>
mediodl update          # بروزرسانی از گیتهاب
mediodl restart
```

داخل تلگرام: `/admin`

## 🔄 بروزرسانی

```bash
mediodl update
# یا دستی:
cd /opt/mediodl-bot && git pull && ./venv/bin/pip install -r requirements.txt && systemctl restart mediodl-bot
# یا داخل تلگرام: /admin → 🔄 بروزرسانی
```

## 💾 فایل تا 2 گیگ — پرمیوم می‌خواهد؟

**خیر!** سقف 50MB مربوط به Bot API رسمی است، نه پرمیوم. برای 2GB:
```bash
# API_ID/HASH از my.telegram.org
nano /opt/mediodl-bot/.env  # BOT_API_SERVER=127.0.0.1 BOT_API_PORT=8081
docker compose -f docker/docker-compose.yml up -d telegram-bot-api
systemctl restart mediodl-bot
```
هیچ پورتی روی 80/443/8000 اشغال نمی‌شود.

## 🛡️ هم‌زیستی

| | 3x-ui | D_bot | MediGo |
|---|---|---|---|
| مسیر | `/usr/local/x-ui` | `/opt/d-bot` | `/opt/mediodl-bot` |
| CLI | `x-ui` | `dbot` | `mediodl` |
| سرویس | `x-ui.service` | api/postgres/redis | `mediodl-bot.service` |
| پورت | inboundها | 80/443/8000 | هیچ (polling) |
| DB | SQLite/Postgres | Postgres | SQLite |

جزئیات: [docs/ANALYSIS_FA.md](docs/ANALYSIS_FA.md)

---
<a name="english"></a>
## English

Professional bot for 9 platforms (YouTube, Instagram, TikTok, Pinterest, Twitter/X, Facebook, SoundCloud, Spotify, Threads). Each link = high-quality video + separate audio. Features captcha, quality picker, auto-delete, log channel, advanced stats, fun mode, and coexistence-safe one-line installer.

<div align="center">

`bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)`

**MediGo — ساخته شده برای کیفیت، فان و هم‌زیستی بی‌دردسر** 😎

</div>
