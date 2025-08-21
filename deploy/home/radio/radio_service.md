# 1. Получить куки YouTube ~/cookies.txt

- Установить в Chrome GetCookies.txt
- Дать доступ расширению в режим инкогнито и прикрепить к адресной строке
- Зайти в режим инкогнито
- Зайти на YouTube под левым аккаунтом, который не жалко
- Скачать куки через GetCookies.txt
- Скинуть их в ~/cookies.txt

# 2. Сформировать playlist.txt и скинуть его ~/playlist.txt

# 3. Настроить папки и права доступа

```bash
    sudo apt install -y acl

    sudo usermod -aG www-data radio

    sudo install -d -m 2775 -o radio -g www-data /var/cache/radio
    sudo install -d -m 2775 -o radio -g www-data /var/www/html
    sudo install -d -m 2775 -o radio -g www-data /var/www/hls/ts
    sudo install -d -m 2775 -o radio -g www-data /var/www/hls/mp4

    sudo chmod g+s /var/cache/radio /var/www/html /var/www/hls /var/www/hls/ts /var/www/hls/mp4

    sudo setfacl -R -m g:www-data:rX /var/www/html
    sudo setfacl -R -m g:www-data:rwx /var/www/hls /var/www/hls/ts /var/www/hls/mp4
    sudo setfacl -R -m d:g:www-data:rwx /var/www/hls /var/www/hls/ts /var/www/hls/mp4
```

# 4. Убедится, что настройки сервиса на месте /etc/systemd/system/radio.service

Обновить демон

```bash
    sudo systemctl daemon-reexec
```

# 5. Создать и запустить сервис

```bash
    sudo chown -R radio:radio "/home/radio"
    find "/home/radio" -type d -exec chmod 755 {} +
    find "/home/radio" -type f -exec chmod 644 {} +
    find "/home/radio" -type f -name "*.sh" -exec chmod 755 {} +

    sudo chown radio:radio /home/radio/radio.sh
    sudo chown radio:radio /home/radio/health_check.sh

    chmod +x ~/radio.sh

    chmod +x ~/health_check.sh

    sudo systemctl enable radio.service

    sudo systemctl start radio.service

    sudo systemctl status radio.service
```

Перезапуск

```bash
    sudo systemctl restart radio.service
```

Если изменились настройки сервиса

```bash
    sudo systemctl daemon-reload
```

Логи

```bash
    # последние записи
    sudo journalctl -u radio.service -n 50 --no-pager

    # следить в реальном времени
    sudo journalctl -u radio.service -f -e

    # полный лог с самого запуска
    sudo journalctl -u radio.service
```

# 6. Очистка файлов

```bash
    sudo find /var/www/hls/ts  -type f -delete
    sudo find /var/www/hls/mp4 -type f -delete
    sudo find /var/www/hls     -maxdepth 1 -type f \( -name '*.m3u8' -o -name '*.tmp' \) -delete

    sudo find /var/cache/radio -type f -mtime +7 -delete
```

# 6. Остановка и удаление

```bash
    sudo systemctl stop radio.service

    sudo systemctl disable radio.service

    sudo rm /etc/systemd/system/radio.service

    sudo systemctl daemon-reexec
```
