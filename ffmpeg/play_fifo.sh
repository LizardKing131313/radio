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

rm -f "$FIFO"; mkfifo "$FIFO"

# --- 1) ЕДИНЫЙ ЭНКОДЕР -> ICECAST (НЕ перезапускается)
ffmpeg -nostdin -hide_banner -nostats -loglevel warning -re \
  -f s16le -ar 44100 -ac 2 -i "$FIFO" \
  -af "asetrate=44100*1.01,aresample=44100" \
  -c:a aac -b:a "$BITRATE" -f adts \
  -content_type audio/aac \
  "$ICE_URL" &
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

# --- 3) Получаем прямой аудио-URL (TV -> iOS) с ретраями
resolve_audio_url(){
  local url="$1" out=""
  for client in tv ios; do
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
  silence_start  # держим поток тишиной, пока ищем ссылку

  local src
  if ! src="$(resolve_audio_url "$url")"; then
    echo "❌ не смог получить прямой URL — скип"
    return 1
  fi

  # стопим тишину, даём реальный звук
  silence_stop
  ffmpeg -nostdin -hide_banner -loglevel error -re \
    -user_agent "$UA" -fflags +nobuffer -timeout 5000000 \
    -i "$src" -vn \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO"

  # вернём тишину на стык, пока готовим следующий
  silence_start
}

# Стартуем тишину заранее, чтобы поток был живой сразу
silence_start

# --- 5) Основной цикл по плейлисту
while IFS= read -r line; do
  play_one "$line" || echo "❌ пропустил: $line"
done < "$PL"

# После плейлиста оставим тишину, чтобы поток не отвалился
wait "$ENC_PID"
