sudo apt install -y ffmpeg
sudo mkdir -p /var/www/radio
sudo chown -R www-data:www-data /var/www/radio
sudo chmod 775 /var/www/radio

sudo nginx -t && sudo systemctl reload nginx

cloudflared tunnel --no-autoupdate --edge-ip-version auto --url http://127.0.0.1:80



pkill -f '/tmp/radio.pcm' 2>/dev/null || true
pkill -f 'ffmpeg .*hls_time' 2>/dev/null || true


cloudflared tunnel login


cloudflared tunnel create radio-tunnel


2b335c8f-c4a0-426b-a373-b83d2c16871f


sudo mkdir -p /etc/cloudflared


sudo nano /etc/cloudflared/config.yml


tunnel: radio-tunnel
credentials-file: /etc/cloudflared/2b335c8f-c4a0-426b-a373-b83d2c16871f.json

ingress:
  - hostname: radio.govnovoz-fm.fun
    service: http://127.0.0.1:80
  - service: http_status:404


cloudflared tunnel route dns radio-tunnel radio.govnovoz-fm.fun


cloudflared tunnel run radio-tunnel


sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

sudo cp /home/radio/.cloudflared/2b335c8f-c4a0-426b-a373-b83d2c16871f.json /etc/cloudflared/

sudo cloudflared service install
sudo systemctl enable --now cloudflared


sudo systemctl restart govnovoz-radio

# посмотреть последние ошибки
sudo journalctl -u govnovoz-radio -n 100 --no-pager

# остановить/отключить
sudo systemctl stop govnovoz-radio
sudo systemctl disable govnovoz-radio

# радио
sudo systemctl status govnovoz-radio
sudo journalctl -u govnovoz-radio -f   # смотреть живые логи

# туннель
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
