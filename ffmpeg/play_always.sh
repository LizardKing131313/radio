#!/usr/bin/env bash
# UTF-8, без BOM
set -Eeuo pipefail
exec </dev/null

ICE_URL="icecast://source:hackme@5.45.94.101:8443/stream"  # порт свой
BITRATE="160k"
FIFO="/tmp/radio.pcm"
PL="$HOME/playlist.txt"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"

cleanup(){ pkill -P "$$" || true; rm -f "$FIFO"; }
trap cleanup EXIT INT TERM

# Нормализуем плейлист
sed -i 's/\r$//' "$PL" 2>/dev/null || true
sed -i 's/^tps:\/\//https:\/\//; s/^ps:\/\//https:\/\//' "$PL" 2>/dev/null || true

rm -f "$FIFO"; mkfifo "$FIFO"

rm -f "$FIFO"; mkfifo "$FIFO"; chmod 666 "$FIFO"

# ---------- ДЕРЖИМ ЭНКОДЕР ЖИВЫМ ВСЕГДА ----------
start_encoder_loop() {
  while true; do
    ffmpeg -nostdin -hide_banner -nostats -loglevel warning -re \
      -f s16le -ar 44100 -ac 2 -i "$FIFO" \
      -af "asetrate=44100*1.01,aresample=44100" \
      -c:a aac -b:a "$BITRATE" -f adts \
      -content_type audio/aac \
      "$ICE_URL" || true
    echo "[enc] encoder died, restarting in 1s..."
    sleep 1
  done
}
start_encoder_loop &
ENC_PID=$!

# ---------- ТИШИНА, КОГДА НЕТ ТРЕКОВ ----------
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

# ---------- РЕЗОЛВИМ ПРЯМОЙ АУДИО-URL С РЕТРАЯМИ ----------
resolve_audio_url(){
  local url="$1" out=""
  for client in tv ios web; do
    for try in 1 2 3 4; do
      out="$(yt-dlp --force-ipv4 \
        --extractor-args "youtube:player_client=${client}" \
        -f bestaudio -g "$url" 2>/dev/null || true)"
      [[ -n "$out" ]] && { printf '%s\n' "$out"; return 0; }
      sleep $((try*2))
    done
  done
  return 1
}

# ---------- ИГРАЕМ ОДИН ТРЕК, ПАДЕНИЯ НЕ ДОПУСКАЕМ ----------
play_one(){
  local url="${1//$'\r'/}"
  [[ -z "$url" || "$url" =~ ^# ]] && return 0
  [[ "$url" =~ ^tps:// ]] && url="ht${url}"
  [[ "$url" =~ ^ps://  ]] && url="htt${url}"

  echo "▶ $url"
  silence_start

  local src=""
  if ! src="$(resolve_audio_url "$url")"; then
    echo "❌ no direct audio url, skip"
    return 0
  fi

  silence_stop
  # Гоним аудио в FIFO; если сорвётся — просто выходим из функции (скрипт жив)
  ffmpeg -nostdin -hide_banner -loglevel warning -re \
    -user_agent "$UA" -fflags +nobuffer \
    -rw_timeout 15000000 -timeout 15000000 \
    -i "$src" -vn -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" 2>/dev/null || true

  # На стык — тишину
  silence_start
}

# ---------- БЕСКОНЕЧНО ВЕРТИМ ПЛЕЙЛИСТ ----------
silence_start
while true; do
  # На каждый круг перечитываем плейлист (вдруг ты его обновил)
  if [[ -f "$PL" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      play_one "$line"
    done < "$PL"
  else
    echo "⚠ нет $PL — сплю 5с"
    sleep 5
  fi
  # пауза между кругами
  sleep 2
done

# (теоретически недостижимо)
wait "$ENC_PID"
