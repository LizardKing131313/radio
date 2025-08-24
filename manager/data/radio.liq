# --- Settings (LS 2.x)
settings.server.telnet.set(true)
settings.server.telnet.bind_addr.set("127.0.0.1")
settings.server.telnet.port.set(1234)
settings.log.level.set(4)

# --- Paths
hot_dir      = "/opt/radio/cache/hot"
cold_dir     = "/opt/radio/cache/cold"
fifo_wav     = "/opt/radio/runtime/fifo/radio.wav"
np_txt_file  = "/opt/radio/runtime/info/nowplaying.txt"

# --- Sources
hot  = playlist(mode="random", reload_mode="watch", hot_dir)
cold = playlist(mode="random", reload_mode="watch", cold_dir)

base = fallback(track_sensitive=true, [hot, cold])
base = audio_to_stereo(base)

# --- DSP (plugin-free)
base = normalize(target=-14.0, base)
base = crossfade(smart=true, duration=6.0, base)

# --- Requests
rq = request.queue(id="rq")

# --- Infallible tail (silence, not a beep)
silence = blank(duration=0.5)     # короткая тишина, а не бесконечный "трек"
program_raw = fallback(track_sensitive=false, [rq, base, silence])

# --- Now Playing helpers
def np_format_line(m) =
  title  = list.assoc(default="Unknown Title",  "title",  m)
  artist = list.assoc(default="Unknown Artist", "artist", m)
  album  = list.assoc(default="",               "album",  m)
  if album == "" then "#{artist} - #{title}"
  else "#{artist} - #{title} [#{album}]" end
end

def write_nowplaying(m) =
  # Plain text (one line)
  file.write(append=false, data=np_format_line(m), np_txt_file)

  # Simple KV for downstream JSON (no plugins needed)
  title  = list.assoc(default="Unknown Title",  "title",  m)
  artist = list.assoc(default="Unknown Artist", "artist", m)
  album  = list.assoc(default="",               "album",  m)
  kv = "title=#{title}\nartist=#{artist}\nalbum=#{album}\n"
  file.write(append=false, data=kv, np_txt_file ^ ".kv")
end

# Attach handler on infallible source
program = source.on_metadata(program_raw, write_nowplaying)

# --- Output: FIFO WAV for ffmpeg
# Ensure FIFO exists: mkfifo /opt/radio/runtime/fifo/radio.wav
output.file(%wav, fifo_wav, program)


# s = sine() # тестовый генератор
# out = output.dummy(s) # чтобы процесс не умирал
