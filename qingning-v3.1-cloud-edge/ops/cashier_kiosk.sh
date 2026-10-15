#!/usr/bin/env bash
# 只负责树莓派桌面浏览器，不修改 SSH、Wi-Fi 和系统默认容器。
set -u
for n in $(seq 1 35); do
  if curl -fsS http://127.0.0.1:18080/health >/dev/null 2>&1; then break; fi
  sleep 2
done
if command -v chromium >/dev/null 2>&1; then BROWSER=chromium
elif command -v chromium-browser >/dev/null 2>&1; then BROWSER=chromium-browser
else echo "未找到 Chromium，请先安装图形浏览器（桌面版 Raspberry Pi OS）" >&2; exit 1; fi
mkdir -p "$HOME/.config/pi-cafe-classroom-browser"
exec "$BROWSER" --user-data-dir="$HOME/.config/pi-cafe-classroom-browser" \
  --no-first-run --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
  --disable-features=Translate --kiosk http://127.0.0.1:18080/cashier
