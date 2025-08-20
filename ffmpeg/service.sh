sudo tee /etc/systemd/system/govnovoz-radio.service >/dev/null <<'UNIT'
[Unit]
Description=Govnovoz FM - 24/7 radio (FIFO -> Icecast + HLS)
After=network-online.target nginx.service
Wants=network-online.target

[Service]
User=radio
Group=radio
WorkingDirectory=/home/radio
Environment=HOME=/home/radio
Environment=XDG_CACHE_HOME=/home/radio/.cache
Environment=PATH=/home/radio/.local/bin:/usr/local/bin:/usr/bin:/bin
# на всякий: больше файловых дескрипторов и чуть приоритет
LimitNOFILE=65536
Nice=-5
# перезапускать, если упало
Restart=always
RestartSec=2
# сам скрипт (он уже делает и Icecast, и HLS)
ExecStart=/home/radio/play_always_mp4.sh
# не спрашивать sudo-пароль внутри (но мы sudo не используем)
TTYPath=/dev/null
NoNewPrivileges=true
TimeoutStopSec=20
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNIT
