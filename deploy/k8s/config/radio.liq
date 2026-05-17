# --- Настройки Liquidsoap 2.x
# В локальном Docker Desktop контейнер идет от root; Liquidsoap требует явного разрешения.
settings.init.allow_root.set(true)
settings.server.telnet.set(true)
settings.server.telnet.bind_addr.set("127.0.0.1")
settings.server.telnet.port.set(1234)
settings.log.level.set(3)
settings.charset.max_string_length.set(4096)

# --- Пути внутри pod
hot_dir      = "/opt/radio/cache/hot"
cold_dir     = "/opt/radio/cache/cold"
fifo_wav     = "/opt/radio/runtime/fifo/radio.wav"
np_txt_file  = "/opt/radio/runtime/info/nowplaying.txt"

# --- Источники треков
# request.queue - готовая очередь Liquidsoap. Python только пушит URI через
# telnet-команду request_queue.push, а не управляет аудиопроцессами сам.
queue_source = request.queue()
hot  = playlist(mode="random", reload_mode="watch", hot_dir)
cold = playlist(mode="random", reload_mode="watch", cold_dir)

# Не используем fallback(hot, cold): если hot непустой, cold вообще не играет.
# rotate держит hot как приоритетный короткий набор, но основную ротацию берет
# из полного cold-каталога.
library = rotate(weights=[1, 4], transition_length=0.0, [hot, cold])
# Очередь не обрывает текущий трек: queued request стартует на ближайшей
# границе трека, поэтому переключение не дергается посреди композиции.
base = fallback(track_sensitive=true, [queue_source, library])
base = stereo(base)

# --- Обработка звука без внешних плагинов
base = normalize(target=-14.0, base)
# 6 секунд резали хвост трека слишком рано. 2 секунды дают мягкий стык без
# заметного преждевременного переключения.
base = crossfade(duration=2.0, fade_in=1.5, fade_out=1.5, base)

# --- Резервный хвост: тишина вместо падения, если плейлисты пустые
silence = blank(duration=0.5)
program_raw = fallback(track_sensitive=false, [base, silence])

# --- Запись текущего трека для API /current
def np_format_line(m) =
  title  = list.assoc(default="Unknown Title",  "title",  m)
  artist = list.assoc(default="Unknown Artist", "artist", m)
  album  = list.assoc(default="",               "album",  m)
  if album == "" then "#{artist} - #{title}"
  else "#{artist} - #{title} [#{album}]" end
end

def write_nowplaying(m) =
  file.write(append=false, data=np_format_line(m), np_txt_file)
  title  = list.assoc(default="Unknown Title",  "title",  m)
  artist = list.assoc(default="Unknown Artist", "artist", m)
  album  = list.assoc(default="",               "album",  m)
  queue_id = list.assoc(default="", "queue_id", m)
  track_id = list.assoc(default="", "track_id", m)
  kv = "title=#{title}\nartist=#{artist}\nalbum=#{album}\nqueue_id=#{queue_id}\ntrack_id=#{track_id}\n"
  file.write(append=false, data=kv, np_txt_file ^ ".kv")
end

program = source.on_metadata(program_raw, write_nowplaying)

# --- Выход: WAV FIFO, который читает ffmpeg-контейнер
output.file(%wav, fifo_wav, program)
