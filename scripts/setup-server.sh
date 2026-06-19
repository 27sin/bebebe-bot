#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/telegram-parody-bot"
REPO_URL="${1:-https://github.com/27sin/bebebe-bot.git}"
SERVICE_USER="${SUDO_USER:-$USER}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/setup-server.sh"
  exit 1
fi

apt update
apt install -y python3 python3-venv python3-pip git

mkdir -p "$APP_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  sudo -u "$SERVICE_USER" git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
sudo -u "$SERVICE_USER" python3 -m venv .venv
sudo -u "$SERVICE_USER" bash -lc "source .venv/bin/activate && pip install -r requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Created $APP_DIR/.env — edit it and add BOT_TOKEN before starting the bot."
fi

mkdir -p "$APP_DIR/data"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"

cat > /etc/systemd/system/telegram-parody-bot.service <<EOF
[Unit]
Description=Telegram Parody Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable telegram-parody-bot

cat > /etc/sudoers.d/telegram-parody-bot-deploy <<EOF
$SERVICE_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart telegram-parody-bot, /bin/systemctl is-active telegram-parody-bot
EOF
chmod 440 /etc/sudoers.d/telegram-parody-bot-deploy

echo "Setup complete."
echo "Next steps:"
echo "  1. nano $APP_DIR/.env"
echo "  2. sudo systemctl start telegram-parody-bot"
echo "  3. sudo journalctl -u telegram-parody-bot -f"
