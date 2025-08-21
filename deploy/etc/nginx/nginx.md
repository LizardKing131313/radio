# 1. Установка

```bash
    sudo apt update

    sudo apt install -y nginx

    nginx -v
```

# 2. Добавить конфигурацию в /etc/nginx/conf.d/radio.conf

Выполнить валидацию конфига

```bash
    sudo nginx -t
```

# 3. Запуск

```bash
    sudo systemctl daemon-reload

    sudo systemctl start nginx

    sudo systemctl enable nginx

    sudo systemctl status nginx
```

Просмотр логов

```bash
    tail -f /var/log/nginx/access.log

    tail -f /var/log/nginx/error.log
```

Перезапуск при изменении конфигурации

```bash
    sudo nginx -t

    sudo systemctl restart nginx
```

Перезапуск без потери соединений

```bash
    sudo systemctl reload nginx
```

# 4. Остановка и удаление

```bash
    sudo systemctl stop nginx

    sudo systemctl disable nginx

    sudo apt remove --purge nginx nginx-common -y

    sudo rm -rf /etc/nginx

    sudo rm -rf /var/log/nginx
```
