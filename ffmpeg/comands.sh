yt-dlp -f bestaudio -o - "<YOUTUBE_URL>" \
| ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
    -vn -af "asetrate=44100*1.01,aresample=44100" \
    -c:a aac -b:a 160k -f adts \
    -content_type audio/aac \
    "icecast://source:hackme@5.45.94.101:8000/stream"


ffmpeg -re -i input.mp3 \
  -vn -af "asetrate=44100*1.01,aresample=44100" \
  -c:a aac -b:a 160k -f adts \
  -content_type audio/aac \
  "icecast://source:hackme@5.45.94.101:8000/stream"


yt-dlp -f bestaudio -o - "https://www.youtube.com/watch?v=Zk4tSCyPG38" \
| ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
    -vn -af "asetrate=44100*1.01,aresample=44100" \
    -c:a aac -b:a 160k -f adts \
    -content_type audio/aac \
    "icecast://source:hackme@5.45.94.101:8000/stream"


ffmpeg -re -f lavfi -i "sine=frequency=440:sample_rate=44100:duration=10" \
  -vn -af "asetrate=44100*1.01,aresample=44100" \
  -c:a aac -b:a 160k -f adts \
  -content_type audio/aac \
  "icecast://source:hackme@5.45.94.101:8000/stream"


~/.local/bin/yt-dlp -f bestaudio -o - --extractor-args "youtube:player_client=ios" "https://www.youtube.com/watch?v=Zk4tSCyPG38" \
| ffmpeg -hide_banner -nostats -loglevel warning -re -i - \
    -vn -af "asetrate=44100*1.01,aresample=44100" \
    -c:a aac -b:a 160k -f adts -content_type audio/aac \
    "icecast://source:hackme@5.45.94.101:8000/stream"




yt-dlp --force-ipv4 --extractor-args "youtube:player_client=tv" -f bestaudio -o - "https://youtu.be/Zk4tSCyPG38" \
| ffmpeg -re -i - -vn -af "asetrate=44100*1.01,aresample=44100" -c:a aac -b:a 160k -f adts -content_type audio/aac "icecast://source:hackme@5.45.94.101:8000/stream"
