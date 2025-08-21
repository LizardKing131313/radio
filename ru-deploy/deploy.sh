#!/usr/bin/env bash
set -euo pipefail

# =========[ НАСТРОЙКИ ]=========
DOMAIN="ru.radio.govnovoz-fm.fun"        # твой домен (который укажешь в DNS на RU-VPS)
EMAIL="lizardking131313@gmail.com"             # почта для Let's Encrypt
UPSTREAM_HOST="radio.govnovoz-fm.fun"      # сюда впиши: IP NL-VPS ИЛИ хост без CF-прокси, например origin.govnovoz-fm.fun
UPSTREAM_SCHEME="https"               # https (рекомендовано) или http, если на апстриме нет TLS
# =================================

if [[ "$EUID" -ne 0 ]]; then
  echo "Запусти от root (sudo su)."; exit 1
fi

if ! command -v apt >/dev/null; then
  echo "Этот скрипт для Ubuntu/Debian (apt)."; exit 1
fi

echo "[1/7] Обновляем пакеты…"
apt update -y
apt install -y nginx certbot python3-certbot-nginx ca-certificates curl

echo "[2/7] Базовый HTTP-вирт-хост для валидации LE…"
cat >/etc/nginx/sites-available/${DOMAIN}.conf <<NGXHTTP
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # Прямо сейчас отдаём только ACME-валидацию
    location /.well-known/acme-challenge/ {
        root /var/www/${DOMAIN};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
NGXHTTP

mkdir -p /var/www/${DOMAIN}
chown -R www-data:www-data /var/www/${DOMAIN}
ln -sf /etc/nginx/sites-available/${DOMAIN}.conf /etc/nginx/sites-enabled/${DOMAIN}.conf
nginx -t && systemctl reload nginx

echo "[3/7] Получаем сертификат LE…"
certbot certonly --nginx -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --non-interactive --redirect

echo "[4/7] Пишем финальный SSL‑reverse proxy конфиг…"
cat >/etc/nginx/sites-available/${DOMAIN}.conf <<'NGXSSL'
# ==== Генерится скриптом; правь через переменные выше ====
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Резолверы на всякий (если UPSTREAM_HOST = имя)
resolver 1.1.1.1 8.8.8.8 valid=300s;
resolver_timeout 5s;

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;

    # LE сертификаты уже получены certbot
    ssl_certificate     /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;

    # Безопасные настройки TLS по-умолчанию (Ubuntu/OpenSSL норм)
    ssl_session_timeout 1d;
    ssl_session_cache shared:MozSSL:10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    # HSTS можно включить после проверки (закомментировано для старта)
    # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Статика/валидация LE всё ещё доступна
    location /.well-known/acme-challenge/ {
        root /var/www/DOMAIN_PLACEHOLDER;
    }

    # Вебсокеты, длинные таймауты и буферы под стрим
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    # SNI к апстриму, если он https c именем
    proxy_ssl_server_name on;

    # Таймауты под медиапоток/HLS
    proxy_connect_timeout 10s;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    send_timeout 600s;

    # Для HLS/длинных ответов лучше не буферить
    proxy_buffering off;

    # Вебсокеты
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    # Главный прокси
    location / {
        proxy_pass https://radio.govnovoz-fm.fun;
        proxy_set_header Host radio.govnovoz-fm.fun;

        proxy_ssl_server_name on;
        proxy_ssl_name radio.govnovoz-fm.fun;

        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;

        proxy_buffering off;
        proxy_read_timeout 600s;
    }

    # Простой healthcheck
    location = /health {
        return 200 'ok';
        add_header Content-Type text/plain;
    }

    # Опционально: ограничить методы
    # if ($request_method !~ ^(GET|HEAD|OPTIONS|POST)$) { return 405; }
}

# Авто-редирект с 80 на 443 остаётся:
server {
    listen 80;
    listen [::]:80;
    server_name DOMAIN_PLACEHOLDER;

    location /.well-known/acme-challenge/ {
        root /var/www/DOMAIN_PLACEHOLDER;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
NGXSSL

# Подставляем переменные в конфиг
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" /etc/nginx/sites-available/${DOMAIN}.conf
sed -i "s#UPSTREAM_SCHEME_PLACEHOLDER#${UPSTREAM_SCHEME}#g" /etc/nginx/sites-available/${DOMAIN}.conf
sed -i "s#UPSTREAM_HOST_PLACEHOLDER#${UPSTREAM_HOST}#g" /etc/nginx/sites-available/${DOMAIN}.conf

echo "[5/7] Проверяем nginx…"
nginx -t
systemctl reload nginx

echo "[6/7] Настраиваем автопродление сертификата…"
systemctl enable --now certbot.timer || true

echo "[7/7] Готово ✅
- Проверь DNS: A-запись ${DOMAIN} должна указывать на IP ЭТОГО RU-VPS (без оранжевого облака в CF).
- Проверь доступность: curl -Iv https://${DOMAIN}/health
- Трафик уходит на ${UPSTREAM_SCHEME}://${UPSTREAM_HOST}
"
