#!/usr/bin/env bash
set -e

echo "=== Govnovoz Radio status ==="

echo -e "\n[ Radio service ]"
systemctl is-active --quiet govnovoz-radio && echo "✅ RUNNING" || echo "❌ STOPPED"
systemctl --no-pager --lines=3 status govnovoz-radio | sed 's/^/   /'

echo -e "\n[ Cloudflared tunnel ]"
systemctl is-active --quiet cloudflared && echo "✅ RUNNING" || echo "❌ STOPPED"
systemctl --no-pager --lines=3 status cloudflared | sed 's/^/   /'

echo -e "\n[ Nginx test ]"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/live/playlist.m3u8 || echo "curl failed"
