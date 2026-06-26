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
queue_source = request.queue()
hot  = playlist(mode="random", reload_mode="watch", hot_dir)
cold = playlist(mode="random", reload_mode="watch", cold_dir)

# Не используем fallback(hot, cold): если hot непустой, cold вообще не играет.
# rotate держит hot как приоритетный короткий набор, но основную ротацию берет
# из полного cold-каталога.
library = rotate(weights=[1, 4], transition_length=0.0, [hot, cold])
# Обычная очередь не обрывает текущий трек.
scheduled = fallback(track_sensitive=true, [queue_source, library])
scheduled = stereo(scheduled)

# --- Обработка звука без внешних плагинов
scheduled = normalize(target=-14.0, scheduled)
# 6 секунд резали хвост трека слишком рано. 2 секунды дают мягкий стык без
# заметного преждевременного переключения.
scheduled = crossfade(duration=2.0, fade_in=1.5, fade_out=1.5, scheduled)

# play-now не делаем вторым request.queue: request.queue становится not ready
# сразу после забора request в current и fallback уходит назад в library.
# Dynamic request.once держит одноразовый source до конца выбранного трека.
play_now_uri = ref(null())
play_now_pending = ref(false)
play_now_active = ref(false)

def play_now_done(_, _) =
  play_now_active := false
end

def play_now_next() =
  uri = play_now_uri()
  if null.defined(uri) then
    play_now_uri := null()
    play_now_pending := false
    play_now_active := true
    request_source = request.once(request.create(null.get(uri)))
    request_source = stereo(request_source)
    request_source = normalize(target=-14.0, request_source)
    request_source = source.on_end(delay={0.0}, request_source, play_now_done)
    null(request_source)
  else
    null()
  end
end

play_now = source.dynamic(id="play_now", track_sensitive=false, play_now_next)

def play_now_push(uri) =
  play_now_uri := null(uri)
  play_now_pending := true
  source.skip(scheduled)
  source.skip(play_now)
  "Queued"
end

def play_now_skip(_) =
  play_now_uri := null()
  play_now_pending := false
  play_now_active := false
  source.skip(play_now)
  "Done"
end

def play_now_flush(_) =
  play_now_uri := null()
  play_now_pending := false
  if play_now_active() then source.skip(play_now) end
  play_now_active := false
  "Done"
end

def play_now_status(_) =
  if play_now_pending() then "pending"
  elsif play_now_active() then "playing"
  else "" end
end

server.register(namespace="play_now", usage="<uri>", description="Play URI immediately.", "push", play_now_push)
server.register(namespace="play_now", description="Skip current play-now source.", "skip", play_now_skip)
server.register(namespace="play_now", description="Clear pending/current play-now source.", "flush", play_now_flush)
server.register(namespace="play_now", description="Return play-now state.", "status", play_now_status)

base = fallback(track_sensitive=false, transition_length=0.0, [play_now, scheduled])

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
  queue_kind = list.assoc(default="", "queue_kind", m)
  kv = "title=#{title}\nartist=#{artist}\nalbum=#{album}\nqueue_id=#{queue_id}\ntrack_id=#{track_id}\nqueue_kind=#{queue_kind}\n"
  file.write(append=false, data=kv, np_txt_file ^ ".kv")
end

program = source.on_metadata(program_raw, write_nowplaying)

# --- Выход: WAV FIFO, который читает ffmpeg-контейнер
output.file(%wav, fifo_wav, program)
