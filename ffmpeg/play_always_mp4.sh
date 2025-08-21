#!/usr/bin/env bash
# UTF-8, без BOM
# Радио-луп: FIFO -> (Icecast + HLS) одним ffmpeg. Без двух писателей в FIFO.
set -Eeuo pipefail
exec </dev/null
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# ===== НАСТРОЙКИ =====
ICE_URL="${ICE_URL:-icecast://source:sokolov@127.0.0.1:8443/stream}"  # поменяй пароль/порт если надо
BITRATE="${BITRATE:-128k}"
FIFO="${FIFO:-/tmp/radio.pcm}"
HLS_DIR="${HLS_DIR:-/var/www/hls}"
YTDLP_COOKIES="$HOME/cookies.txt"
PL="${PL:-$HOME/playlist.txt}"
UA="${UA:-Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0}"

# ===== ХОЗБЛОК =====
cleanup() { pkill -P "$$" >/dev/null 2>&1 || true; rm -f "$FIFO"; }
trap cleanup INT TERM EXIT

mkdir -p "$HLS_DIR"
rm -f "$FIFO"; mkfifo "$FIFO"; chmod 666 "$FIFO"

# Санируем плейлист (на всякий случай CRLF и «обрезанные» схемы)
if [[ -f "$PL" ]]; then
  sed -i 's/\r$//' "$PL" || true
  sed -i 's/^tps:\/\//https:\/\//; s/^ps:\/\//https:\/\//' "$PL" || true
fi

# ===== ЕНКОДЕР: читает FIFO и пишет в Icecast + HLS (без -re) =====
start_encoder() {
  while true; do
    /usr/bin/ffmpeg -nostdin -hide_banner -loglevel warning \
      -f s16le -ar 44100 -ac 2 -i "$FIFO" \
      -af "asetrate=44100*1.01,aresample=44100" \
      \
      -map 0:a -c:a aac -b:a "$BITRATE" -ar 44100 -ac 2 \
      -f adts -content_type audio/aac "$ICE_URL" \
      \
      -map 0:a -c:a aac -b:a "$BITRATE" -ar 44100 -ac 2 \
      -f hls \
      -hls_time 2 \
      -hls_list_size 6 \
      -hls_flags independent_segments+append_list+omit_endlist \
      -hls_segment_type mpegts \
      -hls_segment_filename "$HLS_DIR/seg_%05d.ts" \
      "$HLS_DIR/playlist.m3u8" \
      || true
    echo "[enc] encoder exited, restart in 1s..."
    sleep 1
  done
}

# ===== САЙЛЕНС (держит маунт в паузах). Гарантированно не мешает треку. =====
SIL_PID=""
silence_start() {
  if [[ -n "${SIL_PID:-}" ]] && kill -0 "$SIL_PID" 2>/dev/null; then return; fi
  /usr/bin/ffmpeg -nostdin -hide_banner -loglevel error \
    -f lavfi -i anullsrc=r=44100:cl=stereo \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" &  SIL_PID=$!
}
silence_stop() {
  if [[ -n "${SIL_PID:-}" ]]; then kill "$SIL_PID" 2>/dev/null || true; SIL_PID=""; fi
}

# ===== yt-dlp: достаём прямой аудио-URL с ретраями и разными клиентами =====
resolve_audio_url() {
  local url="$1" out=""
  for client in tv ios web; do
    for try in 1 2 3; do
      out="$(yt-dlp --force-ipv4 \
        --cookies "$YTDLP_COOKIES" \
        --user-agent "Mozilla/5.0" \
        --extractor-args "youtube:player_client=${client}" \
        -f bestaudio -g "$url" 2>/dev/null || true)"
      [[ -n "$out" ]] && { printf '%s\n' "$out"; return 0; }
      sleep $((try*2))
    done
  done
  return 1
}

# ===== Лив трека в FIFO (только здесь -re) =====
play_one() {
  local url="${1//$'\r'/}"
  [[ -z "$url" || "$url" =~ ^# ]] && return 0
  [[ "$url" =~ ^tps:// ]] && url="ht${url}"
  [[ "$url" =~ ^ps://  ]] && url="htt${url}"
  echo "▶ $url"

  local src
  if ! src="$(resolve_audio_url "$url")"; then
    echo "❌ resolve failed, skip"
    return 1
  fi

  silence_stop
  /usr/bin/ffmpeg -nostdin -hide_banner -loglevel error -re \
    -user_agent "$UA" \
    -rw_timeout 60000000 \
    -reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 \
    -reconnect_on_network_error 1 -reconnect_delay_max 5 \
    -i "$src" -vn \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" || true
  silence_start
}

# ===== Стартуем =====
silence_start
start_encoder & ENC_PID=$!

while true; do
  if [[ -f "$PL" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      play_one "$line" || true
      sleep 1  # маленькая пауза между треками, сайленс держит маунт
    done < "$PL"
  else
    echo "⚠ нет $PL — жду 5с"
    sleep 5
  fi
done

wait "$ENC_PID"
