#!/usr/bin/env bash
# UTF-8, без BOM
# Радио: FIFO -> (Icecast + HLS TS) одним ffmpeg. Без двойных читателей FIFO.
set -Eeuo pipefail
exec </dev/null
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# === НАСТРОЙКИ ===
ICE_URL="icecast://source:sokolov@127.0.0.1:8443/stream"  # поменяй порт/пароль при нужде
BITRATE="128k"
FIFO="/tmp/radio.pcm"
PL="$HOME/playlist.txt"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"
HLS_DIR="/var/www/hls"     # сюда будут писаться HLS сегменты (.ts) и playlist.m3u8

# === ХОЗБЛОК ===
cleanup(){ pkill -P "$$" 2>/dev/null || true; rm -f "$FIFO"; }
trap cleanup EXIT INT TERM

# Подчистим плейлист
sed -i 's/\r$//' "$PL" 2>/dev/null || true
sed -i 's/^tps:\/\//https:\/\//; s/^ps:\/\//https:\/\//' "$PL" 2>/dev/null || true

# Гарантируем каталог под HLS (пишем от пользователя radio)
mkdir -p "$HLS_DIR" || true

# FIFO для PCM
rm -f "$FIFO"; mkfifo "$FIFO"; chmod 666 "$FIFO"

# === ЕДИНЫЙ ЭНКОДЕР: читает FIFO и одновременно пишет в Icecast + HLS ===
start_encoder_hls() {
  while true; do
    /usr/bin/ffmpeg -nostdin -hide_banner -loglevel warning -re \
      -f s16le -ar 44100 -ac 2 -i "$FIFO" \
      -af "asetrate=44100*1.01,aresample=44100" \
      \
      -map 0:a -c:a aac -b:a "$BITRATE" \
      -f adts -content_type audio/aac "$ICE_URL" \
      \
      -map 0:a -c:a aac -b:a "$BITRATE" \
      -f hls -hls_time 4 -hls_list_size 30 \
      -hls_flags independent_segments+append_list \
      -hls_segment_filename "$HLS_DIR/seg_%05d.ts" \
      "$HLS_DIR/playlist.m3u8" \
      || true
    echo "[enc] ffmpeg encoder exited, restart in 1s..."
    sleep 1
  done
}
start_encoder_hls &
ENC_PID=$!

# === ТИШИНА, пока готовим следующий трек (держит маунт живым) ===
SIL_PID=""
silence_start() {
  if [[ -n "${SIL_PID:-}" ]] && kill -0 "$SIL_PID" 2>/dev/null; then return; fi
  /usr/bin/ffmpeg -nostdin -hide_banner -loglevel error \
    -f lavfi -i anullsrc=r=44100:cl=stereo \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" &
  SIL_PID=$!
}
silence_stop() {
  if [[ -n "${SIL_PID:-}" ]]; then kill "$SIL_PID" 2>/dev/null || true; SIL_PID=""; fi
}

# === Получаем прямой аудио-URL (ретраи на YouTube) ===
resolve_audio_url() {
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

# === Проигрываем один трек в FIFO (без агрессивных таймаутов) ===
play_one() {
  local url="${1//$'\r'/}"
  [[ -z "$url" || "$url" =~ ^# ]] && return 0
  [[ "$url" =~ ^tps:// ]] && url="ht${url}"
  [[ "$url" =~ ^ps://  ]] && url="htt${url}"

  echo "▶ $url"
  silence_start

  local src
  if ! src="$(resolve_audio_url "$url")"; then
    echo "❌ direct url failed, skip"
    return 1
  fi

  silence_stop
  /usr/bin/ffmpeg -nostdin -hide_banner -loglevel error -re \
    -user_agent "$UA" -rw_timeout 30000000 \
    -i "$src" -vn \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" || true

  silence_start
}

# === Бесконечный цикл по плейлисту ===
silence_start
while true; do
  if [[ -f "$PL" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      play_one "$line" || echo "skip: $line"
    done < "$PL"
  else
    echo "⚠ нет $PL — сплю 5с"; sleep 5
  fi
  sleep 2
done

wait "$ENC_PID"
