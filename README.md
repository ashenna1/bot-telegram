# MediODL Bot — Professional Telegram Media Downloader

> **فارسی** | [English](#english) | [تحلیل هم‌زیستی](docs/ANALYSIS_FA.md)

یک ربات تلگرام **حرفه‌ای، ساده و پرسرعت** برای دانلود از **YouTube, Instagram, TikTok** ساخته شده با **Aiogram 3 + yt-dlp** — هر لینک را به صورت **ویدیو با بهترین کیفیت + فایل صوتی جدا** تحویل می‌دهد.

---

## ✨ ویژگی‌ها

| قابلیت | توضیح |
|---|---|
| 🔴 **YouTube** | ویدیو، Shorts، Embed (1080p) |
| 📸 **Instagram** | پست، Reels، Stories |
| 🎵 **TikTok** | ویدیو + vm/vt لینک |
| 🎬 **دو خروجی** | هر درخواست = ویدیو (mp4) + صدا (mp3) جداگانه |
| 🙄 **ری‌اکشن** | روی پیام لینک فوراً 🙄 (در حال بررسی) |
| 🔒 **عضویت اجباری** | چند کانال اجباری با چک `getChatMember` |
| 📣 **تبلیغات** | متن+عکس+دکمه، نمایش هر N دانلود |
| 🍪 **کوکی** | آپلود cookies.txt برای محتوای خصوصی/محدود |
| 👑 **پنل ادمین** | کامل داخل تلگرام — بدون نیاز به سایت جدا |
| 🚀 **نصب تک‌دستوری** | یک خط در اوبونتو — هم‌زیستی تضمین‌شده با 3x-ui و D_bot |

### 👑 پنل ادمین (داخل تلگرام `/admin`)

```
📊 آمار (روزانه/هفتگی, کاربران, دانلودها, حجم)
⚙️ تنظیمات (کیفیت, کپشن, پیام خوش‌آمد, محدودیت ساعتی, حالت تعمیر)
📢 کانال‌های اجباری (افزودن/حذف/تغییر وضعیت, چندتایی)
📣 تبلیغات (افزودن با عکس+دکمه, تناوب نمایش)
👥 کاربران (لیست, جستجو, بن/آنبن, پیام مستقیم)
📥 لاگ دانلودها
🍪 کوکی‌ها (آپلود per-platform)
🔄 وضعیت سرویس و ریستارت
📣 پیام همگانی (Broadcast به همه)
🧹 پاکسازی tmp
```

---

## 🚀 نصب تک‌دستوری (Ubuntu 20.04/22.04/24.04)

> **سازگار با سروری که `MHSanaei/3x-ui` و `officialdarvish/D_bot` رویش نصب است — هیچ پورت/سرویس/فایلی را بازنویسی نمی‌کند.**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

نصاب به صورت تعاملی `BOT_TOKEN` و `ADMIN_IDS` را می‌پرسد. همچنین می‌توان از قبل متغیر محیطی داد:

```bash
BOT_TOKEN="1234567890:AAH..." ADMIN_IDS="123456789,987654321" \
bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
```

### بعد از نصب

```bash
mediodl status        # وضعیت + منابع + چک هم‌زیستی
mediodl logs -f       # لاگ زنده
mediodl token <TOKEN> # تغییر سریع توکن
mediodl admin <ID>    # افزودن ادمین
mediodl restart       # ریستارت
systemctl status mediodl-bot
```

در تلگرام: به ربات پیام بده → `/admin`

---

## 🔧 مدیریت

| دستور | کاربرد |
|---|---|
| `mediodl status` | وضعیت سرویس، RAM/دیسک، DB، هم‌زیستی |
| `mediodl logs` / `-f` | لاگ journal |
| `mediodl restart` | ریستارت ربات |
| `mediodl config` | ویرایش `.env` |
| `mediodl backup` | بکاپ DB+کوکی‌ها به `/root/` |
| `mediodl cleanup` | پاکسازی `tmp/` |
| `mediodl update` | `git pull` + نصب وابستگی‌ها + ریستارت |
| `mediodl uninstall` | حذف کامل (ایمن) |

---

## 📁 ساختار

```
bot/                    # سورس ربات
  config.py             # تنظیمات
  db.py                 # SQLite (بدون نیاز به Postgres)
  handlers/user.py      # لینک → ویدیو+صدا
  handlers/admin.py     # پنل کامل
  utils/downloader.py   # yt-dlp + ffmpeg wrapper
  keyboards/inline.py
install.sh              # نصاب اصلی (تک‌دستوری)
uninstall.sh
systemctl/mediodl-bot.service  # سرویس ایزوله (CPU/RAM محدود)
scripts/mediodl         # CLI مدیریت
docker/                 # اجرای اختیاری با Docker
docs/ANALYSIS_FA.md     # تحلیل عمیق فارسی
```

---

## 🛡️ هم‌زیستی (Coexistence)

| مؤلفه | 3x-ui | D_bot | MediODL (این ربات) |
|---|---|---|---|
| مسیر | `/usr/local/x-ui`, `/etc/x-ui`, `/usr/bin/x-ui` | `/opt/d-bot`, `/opt/mikrotik-panel` | **`/opt/mediodl-bot`** |
| CLI | `x-ui` | `dbot` / `d-bot` | **`mediodl` / `mediabot`** |
| سرویس | `x-ui.service` | `api`, `postgres`, `redis` (docker) | **`mediodl-bot.service`** |
| پورت‌ها | پنل + inboundها، `5432` (opt Postgres) | `80/443` (nginx), `8000` (API) | **هیچ — polling، بدون nginx** |
| شبکه | host | `d-bot_default` | **`mediodl_network`** |
| دیتابیس | SQLite/Postgres (host) | Postgres (docker) | **SQLite `/opt/mediodl-bot/data/bot.db`** |

جزئیات کامل: [docs/ANALYSIS_FA.md](docs/ANALYSIS_FA.md)

---

## ❓ FAQ

**فایل بالای 50MB چه می‌شود؟**
تلگرام Bot API رسمی تا 50MB را مستقیم می‌فرستد. برای تا 2GB، Local Bot API را فعال کن — راهنما در `docs/ANALYSIS_FA.md` و `docker/docker-compose.yml` (سرویس اختیاری `telegram-bot-api`).

**کوکی از کجا بیاورم؟**
افزونه Chrome/Firefox: *Get cookies.txt LOCALLY* → خروجی `cookies.txt` → در `/admin` → کوکی‌ها → آپلود.

**ری‌اکشن 🙄 کار نمی‌کند؟**
برخی ایموجی‌ها در Bot API allow-list نیستند. ربات ابتدا 🙄 را امتحان می‌کند و در صورت خطا خودکار به 🤔 می‌افتد.

---

## 📜 لایسنس

MIT — استفاده آزاد.

---

<a name="english"></a>
## English Summary

Professional Telegram bot that downloads from YouTube/Instagram/TikTok and delivers **high-quality video + separate audio** per link. Features instant 🙄 reaction, multi-channel force-join, ads, cookie support, and a full in-Telegram admin panel (`/admin`). One-line Ubuntu installer coexists safely with `3x-ui` and `D_bot` (isolated path `/opt/mediodl-bot`, systemd service `mediodl-bot`, no Nginx/Postgres port conflicts). See Persian docs for full analysis.

---

<div align="center">

**ساخته شده برای کیفیت، سادگی و هم‌زیستی بی‌دردسر**

`bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)`

</div>
