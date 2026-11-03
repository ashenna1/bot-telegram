#!/usr/bin/env bash
set -e
# MediODL - Safe Uninstall (never touches 3x-ui / D_bot)
GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
APP_DIR="/opt/mediodl-bot"
SERVICE="mediodl-bot"

echo -e "${RED}حذف MediODL...${NC}"

if [[ $EUID -ne 0 ]]; then echo "لطفاً با root اجرا کن: sudo bash uninstall.sh"; exit 1; fi

echo -e "${BLUE}[1/4]${NC} توقف و حذف سرویس..."
systemctl stop "$SERVICE" 2>&1 | head || true
systemctl disable "$SERVICE" 2>&1 | head || true
rm -f /etc/systemd/system/mediodl-bot.service
systemctl daemon-reload 2>&1 | head || true
echo "  ✅ سرویس حذف شد"

echo -e "${BLUE}[2/4]${NC} حذف CLI..."
rm -f /usr/local/bin/mediodl /usr/local/bin/mediabot
echo "  ✅ CLI حذف شد"

echo -e "${BLUE}[3/4]${NC} حذف فایل‌های برنامه..."
if [[ -d "$APP_DIR" ]]; then
  echo "  مسیر: $APP_DIR"
  read -p "  آیا بکاپ بگیری؟ (y/N): " ans
  if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
    TS=$(date +%Y%m%d_%H%M%S)
    tar -czf "/root/mediodl-backup-uninstall-$TS.tar.gz" -C /opt mediodl-bot 2>&1 | head
    echo "  ✅ بکاپ: /root/mediodl-backup-uninstall-$TS.tar.gz"
  fi
  rm -rf "$APP_DIR"
  echo "  ✅ پوشه حذف شد"
fi

echo -e "${BLUE}[4/4]${NC} بررسی هم‌زیستی (تضمین عدم آسیب)..."
for p in "/usr/local/x-ui" "/opt/d-bot" "/usr/local/bin/x-ui" "/usr/local/bin/dbot" "/usr/local/bin/d-bot"; do
  [[ -e "$p" ]] && echo "  ✅ محفوظ: $p (دست نخورد)" || echo "  - $p (از قبل نبود)"
done
if systemctl is-active --quiet x-ui 2>&1; then echo "  ✅ x-ui سرویس همچنان فعال"; fi
if docker ps 2>&1 | grep -q d-bot; then echo "  ✅ کانتینرهای D_bot همچنان فعال"; fi

echo
echo -e "${GREEN}✅ حذف کامل شد. سرور و پنل‌های 3x-ui و D_bot بدون تغییر باقی ماندند.${NC}"
