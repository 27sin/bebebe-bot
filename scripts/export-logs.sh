#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/telegram-parody-bot}"
STAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE="/tmp/bebebe-bot-logs-${STAMP}.tar.gz"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if command -v journalctl >/dev/null 2>&1; then
  journalctl -u telegram-parody-bot --no-pager > "$TMP/systemd.log" || true
fi

if [[ -d "$APP_DIR/logs" ]]; then
  cp -a "$APP_DIR/logs/." "$TMP/" 2>/dev/null || true
fi

tar -czf "$ARCHIVE" -C "$TMP" .
echo "$ARCHIVE"
