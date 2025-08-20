#!/usr/bin/env bash
set -Eeuo pipefail

ICE_URL="icecast://source:hackme@5.45.94.101:8443/stream"
BITRATE="160k"

play_url () {
  local url="$1"
  echo "▶ $url"
  # пробуем TV
  if yt-dlp --force-ipv4 --extractor-args "youtube:player_client=tv" -f bestaudio -o - "$url" \
    | ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
        -vn -af "asetrate=44100*1.01,aresample=44100" \
        -c:a aac -b:a "$BITRATE" -f adts -content_type audio/aac "$ICE_URL" ; then
    return 0
  fi
  echo "… TV не прошёл, пробую iOS"
  yt-dlp --force-ipv4 --extractor-args "youtube:player_client=ios" -f bestaudio -o - "$url" \
  | ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
      -vn -af "asetrate=44100*1.01,aresample=44100" \
      -c:a aac -b:a "$BITRATE" -f adts -content_type audio/aac "$ICE_URL" || return 1
}

while IFS= read -r url; do
  [[ -z "$url" || "$url" =~ ^# ]] && continue
  play_url "$url" || echo "❌ пропустил: $url"
  echo "⏭ next…"
done < ~/playlist.txt
