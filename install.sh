#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# MediODL Bot — One-Line Installer for Ubuntu (Coexistence-Safe)
# Repository: https://github.com/ashenna1/bot-telegram
# One-line: bash <(curl -fsSL https://raw.githubusercontent.com/ashenna1/bot-telegram/main/install.sh)
# Coexists with: MHSanaei/3x-ui (/usr/local/x-ui) + officialdarvish/D_bot (/opt/d-bot, nginx 80/443, postgres 5432, redis, docker)
# ==============================================================================

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
REPO_URL="https://github.com/ashenna1/bot-telegram.git"
APP_DIR="/opt/mediodl-bot"
REPO_RAW="https://raw.githubusercontent.com/ashenna1/bot-telegram/main"

info(){ echo -e "${BLUE}[MediODL]${NC} $*"; }
ok(){ echo -e "${GREEN}[MediODL] ✔${NC} $*"; }
warn(){ echo -e "${YELLOW}[MediODL] ⚠${NC} $*"; }
err(){ echo -e "${RED}[MediODL] ✘${NC} $*"; }
die(){ err "$*"; exit 1; }

# --- Banner ---
echo -e "${CYAN}"
cat <<'BANNER'
  __  __          _ _  ___   ___  _
 |  \/  | ___  __| (_) / _ \ |   \| |     Bot
 | |\/| |/ _ \/ _` | | | (_) | |) | |     YouTube • Instagram • TikTok
 |_|  |_|\___/\__,_|_|  \___/|___/|_|___   Video + Separate Audio
                                     |___|  Professional • Coexistence-Safe
BANNER
echo -e "${NC}"
echo -e "${BLUE}Repository:${NC} $REPO_URL"
echo -e "${BLUE}App Dir:   ${NC} $APP_DIR  (ایزوله از 3x-ui و D_bot)"
echo

# --- Root check ---
if [[ $EUID -ne 0 ]]; then die "لطفاً با کاربر root اجرا کن: sudo bash install.sh  یا  sudo bash <(curl -fsSL ...)"; fi

# --- Coexistence pre-flight (never touch existing panels) ---
info "بررسی هم‌زیستی با پنل‌های موجود..."
for p in "/usr/local/x-ui" "/opt/d-bot"; do
  if [[ -e "$p" ]]; then
    ok "شناسایی شد: $p — دست نمی‌زنیم (ایزوله می‌مانیم)"
  fi
done
# Check ports that we MUST NOT occupy
for port in 80 443 8000 5432; do
  if ss -tlnp 2>/dev/null | grep -q ":$port\b"; then
    info "پورت $port در حال استفاده است — ما از آن استفاده نمی‌کنیم (ربات polling است، نیازی به nginx/پورت ندارد)"
  fi
done
# Docker is shared safely via isolated network
if command -v docker &>/dev/null; then
  ok "Docker شناسایی شد (متعلق به D_bot) — ما شبکه جدا mediodl_network می‌سازیم، تداخلی ندارد"
fi
echo

# --- Ask config (interactive or env) ---
BOT_TOKEN="${BOT_TOKEN:-}"
ADMIN_IDS="${ADMIN_IDS:-}"
BRANCH="${BRANCH:-main}"
INSTALL_MODE="${INSTALL_MODE:-native}"  # native | docker (docker optional)

if [[ -t 0 ]]; then
  # Interactive
  if [[ -z "$BOT_TOKEN" ]]; then
    echo -e "${YELLOW}تنظیمات ربات:${NC}"
    echo "  توکن را از @BotFather بگیر ( /newbot )"
    read -rp "  BOT_TOKEN: " BOT_TOKEN || true
  fi
  if [[ -z "$ADMIN_IDS" ]]; then
    echo "  آیدی عددی ادمین را از @userinfobot بگیر (با کاما برای چند ادمین)"
    read -rp "  ADMIN_IDS (مثلاً 123456789): " ADMIN_IDS || true
  fi
fi

if [[ -z "$BOT_TOKEN" ]]; then
  warn "BOT_TOKEN خالی است — نصب ادامه می‌یابد ولی ربات تا تنظیم توکن استارت نمی‌شود."
  warn "بعداً اجرا کن: mediodl token <TOKEN>"
  BOT_TOKEN="REPLACE_WITH_YOUR_BOT_TOKEN"
fi
if [[ -z "$ADMIN_IDS" ]]; then
  warn "ADMIN_IDS خالی است — بعداً: mediodl admin <ID>  یا  nano $APP_DIR/.env"
  ADMIN_IDS=""
fi

# --- System dependencies (minimal, no nginx/postgres disruption) ---
info "نصب پیش‌نیازها (python3, venv, ffmpeg, git, curl, sqlite3, deno)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl sqlite3 ffmpeg unzip jq ca-certificates > /dev/null 2>&1 || \
  apt-get install -y python3 python3-venv python3-pip git curl sqlite3 ffmpeg unzip jq ca-certificates
ok "پیش‌نیازهای سیستمی نصب شد (nginx/postgres/redis دست نخورد)"

# --- Deno (required for yt-dlp JS challenges, esp. YouTube) ---
if ! command -v deno &>/dev/null; then
  info "نصب Deno..."
  curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh > /dev/null 2>&1 || warn "نصب Deno ناموفق — برخی ویدیوهای یوتیوب ممکن است بدون Deno کار نکنند"
  if [[ -f /usr/local/bin/deno ]]; then ok "Deno نصب شد: $(/usr/local/bin/deno --version | head -1)"; fi
else
  ok "Deno موجود است: $(deno --version | head -1)"
fi

# --- Clone / Update repo ---
if [[ -d "$APP_DIR/.git" ]]; then
  info "بروزرسانی سورس از گیتهاب..."
  git -C "$APP_DIR" fetch --quiet
  git -C "$APP_DIR" checkout "$BRANCH" --quiet 2>&1 || true
  git -C "$APP_DIR" pull --rebase --autostash --quiet || warn "git pull ناموفق — ادامه با کد موجود"
else
  if [[ -d "$APP_DIR" && -n "$(ls -A $APP_DIR 2>/dev/null)" ]]; then
    warn "$APP_DIR موجود و غیر خالی است — بکاپ گرفته می‌شود"
    mv "$APP_DIR" "${APP_DIR}.bak.$(date +%Y%m%d%H%M%S)"
  fi
  info "دریافت سورس از گیتهاب..."
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
ok "سورس آماده: $APP_DIR"

# --- Python venv ---
info "ساخت محیط مجازی پایتون..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
ok "وابستگی‌های پایتون نصب شد"

# --- Directories & Permissions ---
mkdir -p "$APP_DIR/data" "$APP_DIR/tmp" "$APP_DIR/cookies" "$APP_DIR/logs"
chmod 700 "$APP_DIR/data" "$APP_DIR/cookies"
chmod 755 "$APP_DIR/tmp"

# --- .env ---
if [[ ! -f "$APP_DIR/.env" ]]; then
  info "ساخت فایل .env..."
  cat > "$APP_DIR/.env" <<ENV
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
BOT_NAME=MediODL
DEFAULT_LANG=fa
MAX_VIDEO_HEIGHT=1080
MAX_UPLOAD_MB=2000
MAX_DURATION_SEC=3600
RATE_LIMIT_PER_HOUR=20
TMP_DIR=$APP_DIR/tmp
DATABASE_PATH=$APP_DIR/data/bot.db
LOG_LEVEL=INFO
ENV
  chmod 600 "$APP_DIR/.env"
  ok ".env ساخته شد"
else
  info ".env موجود است — دست نخورد (برای تغییر: mediodl config)"
  # Update token if provided and not placeholder
  if [[ "$BOT_TOKEN" != "REPLACE_WITH_YOUR_BOT_TOKEN" && -n "$BOT_TOKEN" ]]; then
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$BOT_TOKEN|" "$APP_DIR/.env" || echo "BOT_TOKEN=$BOT_TOKEN" >> "$APP_DIR/.env"
  fi
fi

# --- Systemd service (isolated, CPU/RAM limited) ---
info "نصب سرویس systemd..."
cp -f "$APP_DIR/systemctl/mediodl-bot.service" /etc/systemd/system/mediodl-bot.service
systemctl daemon-reload
systemctl enable mediodl-bot --quiet
ok "سرویس mediodl-bot.service نصب و فعال شد"

# --- CLI tool ---
info "نصب CLI مدیریت..."
cp -f "$APP_DIR/scripts/mediodl" /usr/local/bin/mediodl
chmod +x /usr/local/bin/mediodl
# Also alias /usr/local/bin/mediabot for convenience
ln -sf /usr/local/bin/mediodl /usr/local/bin/mediabot 2>&1 || true
ok "CLI آماده: mediodl (و mediabot)"

# --- Start service ---
if grep -q "REPLACE_WITH_YOUR_BOT_TOKEN" "$APP_DIR/.env"; then
  warn "توکن تنظیم نشده — سرویس استارت نمی‌شود. اول توکن را تنظیم کن:"
  echo -e "  ${CYAN}mediodl token <TOKEN>${NC}   یا   ${CYAN}nano $APP_DIR/.env${NC}"
else
  info "استارت سرویس..."
  systemctl restart mediodl-bot || warn "استارت سرویس ناموفق — لاگ را چک کن: mediodl logs"
  sleep 2
  if systemctl is-active --quiet mediodl-bot; then
    ok "سرویس فعال است ✅"
  else
    warn "سرویس فعال نیست — بررسی: systemctl status mediodl-bot  |  mediodl logs"
    systemctl status mediodl-bot --no-pager -l 2>&1 | head -40 || true
  fi
fi

# --- Optional: Local Bot API for >50MB (isolated docker, no port conflict) ---
# We do NOT auto-start it to avoid surprises. User can enable via: mediodl local-api enable
# The docker-compose in docker/ uses 127.0.0.1:8082 (not 80/443/8000/5432) and isolated network.

# --- Summary ---
echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ نصب MediODL کامل شد!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
echo -e "${CYAN}مدیریت:${NC}"
echo -e "  mediodl status          # وضعیت + منابع + هم‌زیستی"
echo -e "  mediodl logs -f         # لاگ زنده"
echo -e "  mediodl restart         # ریستارت"
echo -e "  mediodl config          # ویرایش .env"
echo -e "  mediodl token <TOKEN>   # تنظیم سریع توکن"
echo -e "  mediodl admin <ID>      # افزودن ادمین"
echo -e "  systemctl status mediodl-bot"
echo
echo -e "${CYAN}پنل ادمین داخل تلگرام:${NC}"
echo -e "  به ربات پیام بده: /admin  (فقط ادمین‌ها)"
echo -e "  • تنظیمات، کانال اجباری، تبلیغات، کوکی، آمار، پیام همگانی"
echo
echo -e "${CYAN}هم‌زیستی تضمین‌شده:${NC}"
echo -e "  • 3x-ui: /usr/local/x-ui و پورت‌های xray دست نخورد"
echo -e "  • D_bot: /opt/d-bot, nginx 80/443, postgres 5432, redis, docker دست نخورد"
echo -e "  • ربات: $APP_DIR + سرویس mediodl-bot (CPU/RAM محدود)"
echo
if grep -q "REPLACE_WITH_YOUR_BOT_TOKEN" "$APP_DIR/.env"; then
  echo -e "${YELLOW}اقدام بعدی:${NC} توکن را تنظیم کن و ریستارت کن:"
  echo -e "  ${BLUE}mediodl token 1234567890:AAH...${NC}"
  echo -e "  ${BLUE}mediodl admin 123456789${NC}  # آیدی خودت"
fi
echo
echo -e "${BLUE}مستندات کامل:${NC} https://github.com/ashenna1/bot-telegram"
echo -e "${BLUE}تحلیل هم‌زیستی:${NC} docs/ANALYSIS_FA.md"
echo
