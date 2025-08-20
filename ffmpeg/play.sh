#!/usr/bin/env bash
set -Eeuo pipefail

ICE_URL="icecast://source:hackme@5.45.94.101:8000/stream"
BITRATE="160k"

while IFS= read -r url; do
  [[ -z "$url" || "$url" =~ ^# ]] && continue
  echo "▶ Now streaming: $url"
  yt-dlp --force-ipv4 --extractor-args "youtube:player_client=tv" -f bestaudio -o - "$url" \
  | ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
      -vn -af "asetrate=44100*1.01,aresample=44100" \
      -c:a aac -b:a "$BITRATE" -f adts \
      -content_type audio/aac \
      "$ICE_URL" || echo "❌ Failed: $url"
  echo "⏭ Next..."
done < ~/playlist.txt
