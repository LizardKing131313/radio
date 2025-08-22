#!/usr/bin/env bash
# UTF-8, без BOM
# Радио-луп: FIFO -> HLS одним ffmpeg. Без Icecast и без генерации тишины.
set -Eeuo pipefail
exec </dev/null
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# ===== НАСТРОЙКИ =====
FIFO="${FIFO:-${XDG_CACHE_HOME:-/var/cache/radio}/radio.pcm}"
HLS_DIR="${HLS_DIR:-/var/www/hls}"
YTDLP_COOKIES="$HOME/cookies.txt"
PL="${PL:-$HOME/playlist.txt}"
UA="${UA:-Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0}"

# ===== ХОЗБЛОК =====
cleanup() { pkill -P "$$" >/dev/null 2>&1 || true; rm -f "$FIFO"; }
trap cleanup INT TERM EXIT

mkdir -p "$HLS_DIR"
mkdir -p "$HLS_DIR" "$HLS_DIR/ts" "$HLS_DIR/mp4"
rm -rf "$HLS_DIR/mp4/"* "$HLS_DIR/ts/"*
mkdir -p "${XDG_CACHE_HOME:-/var/cache/radio}"
rm -f "$FIFO"; mkfifo "$FIFO"; chmod 666 "$FIFO"

# Санируем плейлист (на всякий случай CRLF и «обрезанные» схемы)
if [[ -f "$PL" ]]; then
  sed -i 's/\r$//' "$PL" || true
  sed -i 's/^tps:\/\//https:\/\//; s/^ps:\/\//https:\/\//' "$PL" || true
fi

# ===== ЕНКОДЕР: читает FIFO и пишет в HLS (без -re) =====
start_encoder() {
  while true; do
    /usr/bin/ffmpeg -nostdin -hide_banner -loglevel warning \
      -f s16le -ar 44100 -ac 2 -i "$FIFO" \
      \
      -map 0:a -map 0:a -map 0:a \
      -c:a:0 aac -b:a:0 64k  -ar:0 44100 -ac:0 2 \
      -c:a:1 aac -b:a:1 96k  -ar:1 44100 -ac:1 2 \
      -c:a:2 aac -b:a:2 128k -ar:2 44100 -ac:2 2 \
      \
      -f hls \
      -hls_time 6 \
      -hls_list_size 12 \
      -hls_delete_threshold 14 \
      -hls_flags independent_segments+append_list+delete_segments \
      -hls_start_number_source epoch \
      -master_pl_name playlist.m3u8 \
      -var_stream_map "a:0,name:64k a:1,name:96k a:2,name:128k" \
      -hls_segment_type mpegts \
      -hls_segment_filename "$HLS_DIR/ts/v%v/seg_%05d.ts" \
      "$HLS_DIR/ts/v%v/index.m3u8" \
      \
      -map 0:a -map 0:a -map 0:a \
      -c:a:0 aac -b:a:0 64k  -ar:0 44100 -ac:0 2 \
      -c:a:1 aac -b:a:1 96k  -ar:1 44100 -ac:1 2 \
      -c:a:2 aac -b:a:2 128k -ar:2 44100 -ac:2 2 \
      -f hls \
      -hls_time 6 \
      -hls_list_size 12 \
      -hls_delete_threshold 14 \
      -hls_flags independent_segments+omit_endlist+append_list+delete_segments \
      -hls_start_number_source epoch \
      -master_pl_name playlist.m3u8 \
      -var_stream_map "a:0,name:64k a:1,name:96k a:2,name:128k" \
      -hls_segment_type fmp4 \
      -hls_fmp4_init_filename "init.mp4" \
      -hls_segment_filename "$HLS_DIR/mp4/v%v/seg_%05d.m4s" \
      "$HLS_DIR/mp4/v%v/index.m3u8" \
      || true
    echo "[enc] encoder exited, restart in 1s..."
    sleep 1
  done
}

# ===== yt-dlp: достаём прямой аудио-URL с ретраями и разными клиентами =====
resolve_audio_url() {
  local url="$1" out="" client extra=()
  # Порядок клиентов: web → tv → ios (у ios НЕТ поддержки cookies)
  for client in web tv ios; do
    for try in 1 2 3; do
      extra=(--force-ipv4 --user-agent "Mozilla/5.0" --extractor-args "youtube:player_client=${client}")
      # cookies только не для ios
      [[ "$client" != "ios" && -f "$YTDLP_COOKIES" ]] && extra+=(--cookies "$YTDLP_COOKIES")

      # Мягкий селектор: сначала чистое аудио, иначе любое лучшее
      # ВАЖНО: без --extract-audio/--audio-format, т.к. -g просто печатает ссылку
      out="$(
        yt-dlp -v "${extra[@]}" \
          -f 'bestaudio[ext=m4a]/bestaudio/best' \
          -g "$url" 2> >(tee /tmp/yt.err >&2) || true
      )"

      # Если YouTube вернул “Only images are available” — смысла пытаться дальше этим клиентом нет
      if grep -qi "Only images are available" /tmp/yt.err; then
        out=""
      fi
      rm -f /tmp/yt.err

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

/usr/bin/ffmpeg -nostdin -hide_banner -loglevel warning -re \
    -user_agent "$UA" \
    -rw_timeout 300000000 \
    -reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 \
    -reconnect_on_http_error 4xx,5xx -reconnect_on_network_error 1 -reconnect_delay_max 5 \
    -i "$src" -vn \
    -f s16le -ar 44100 -ac 2 - \
    > "$FIFO" || true
}

# ===== Стартуем =====
start_encoder & ENC_PID=$!
sleep 0.2
exec 3>"$FIFO"

while true; do
  if [[ -f "$PL" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      play_one "$line" || true
      sleep 1  # маленькая пауза между треками; HLS просто держит последний сегмент
    done < "$PL"
  else
    echo "⚠ нет $PL — жду 5с"
    sleep 5
  fi
done

wait "$ENC_PID"
