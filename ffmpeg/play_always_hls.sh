#!/usr/bin/env bash
set -Eeuo pipefail
exec </dev/null  # не читаем STDIN

ICE_URL="icecast://source:hackme@5.45.94.101:8443/stream"
BITRATE="160k"
FIFO="/tmp/radio.pcm"
PL="$HOME/playlist.txt"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"

cleanup(){ pkill -P "$$" || true; rm -f "$FIFO"; }
trap cleanup EXIT INT TERM

# Чистим плейлист от CRLF и битых префиксов
sed -i 's/\r$//' "$PL" 2>/dev/null || true
sed -i 's/^tps:\/\//https:\/\//; s/^ps:\/\//https:\/\//' "$PL" 2>/dev/null || true

rm -f "$FIFO"; mkfifo "$FIFO"; chmod 666 "$FIFO"

# --- 1) ЕДИНЫЙ ffmpeg -> два выхода: ICECAST + HLS
ffmpeg -nostdin -hide_banner -loglevel warning -re \
  -f s16le -ar 44100 -ac 2 -i "$FIFO" \
  -af "asetrate=44100*1.01,aresample=44100" \
  -map 0:a -c:a aac -b:a "$BITRATE" -f adts -content_type audio/aac "$ICE_URL" \
  -map 0:a -c:a aac -b:a "$BITRATE" \
    -f hls -hls_time 5 -hls_list_size 8 \
    -hls_flags delete_segments+independent_segments \
    -master_pl_name master.m3u8 \
    -hls_segment_filename /var/www/radio/seg_%05d.ts \
    /var/www/radio/playlist.m3u8 \
  &
ENC_PID=$!

# --- 2) ФОНОВЫЙ ГЕНЕРАТОР ТИШИНЫ (держит поток, пока нет трека)
SIL_PID=""
silence_start() {
  if [[ -n "${SIL_PID:-}" ]] && kill -0 "$SIL_PID" 2>/dev/null; then return; fi
  ffmpeg -nostdin -hide_banner -loglevel error \
    -f lavfi -i anullsrc=r=44100:cl=stereo \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" &
  SIL_PID=$!
}
silence_stop() {
  if [[ -n "${SIL_PID:-}" ]]; then kill "$SIL_PID" 2>/dev/null || true; SIL_PID=""; fi
}

# --- 3) Получаем прямой аудио-URL (с ретраями)
resolve_audio_url(){
  local url="$1" out=""
  for client in tv ios web; do
    for try in 1 2 3; do
      out="$(yt-dlp --force-ipv4 \
        --extractor-args "youtube:player_client=${client}" \
        -f bestaudio -g "$url" 2>/dev/null || true)"
      [[ -n "$out" ]] && { printf '%s\n' "$out"; return 0; }
      sleep $((try*2))
    done
  done
  return 1
}

# --- 4) Льём один трек в FIFO (пока готовим — идёт тишина)
play_one(){
  local url="${1//$'\r'/}"
  [[ -z "$url" || "$url" =~ ^# ]] && return 0
  [[ "$url" =~ ^tps:// ]] && url="ht${url}"
  [[ "$url" =~ ^ps://  ]] && url="htt${url}"

  echo "▶ $url"
  silence_start

  local src
  if ! src="$(resolve_audio_url "$url")"; then
    echo "❌ не смог получить прямой URL — скип"
    return 1
  fi

  silence_stop
  ffmpeg -nostdin -hide_banner -loglevel error -re \
    -user_agent "$UA" -fflags +nobuffer -timeout 5000000 \
    -i "$src" -vn \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO"

  silence_start
}

# --- 5) Основной цикл по плейлисту (бесконечно)
silence_start
while true; do
  while IFS= read -r line; do
    play_one "$line" || echo "❌ пропустил: $line"
  done < "$PL"
  sleep 2
done

wait "$ENC_PID"
