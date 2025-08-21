#!/usr/bin/env bash
set -e

echo "=== Radio status ==="

echo -e "\n[ Radio service ]"
systemctl is-active --quiet radio.service && echo "✅ RUNNING" || echo "❌ STOPPED"
systemctl --no-pager --lines=3 status radio.service | sed 's/^/   /'

echo -e "\n[ Cloudflared tunnel ]"
systemctl is-active --quiet cloudflared && echo "✅ RUNNING" || echo "❌ STOPPED"
systemctl --no-pager --lines=3 status cloudflared | sed 's/^/   /'

echo -e "\n[ Nginx test ]"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/live/ts/playlist.m3u8 || echo "curl failed"
