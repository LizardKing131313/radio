# 1. Купить домен

# 2. Зарегистрироваться на CF https://dash.cloudflare.com/

# 3. На CF сделать "Connect a domain"

# 4. На панели управления зайти в подключенный домен и в правом меню найти пункт DNS

Скопировать DNS адреса, которые там указанны, и установить их в домен на сайте, где он был куплен

# 5. Установить CF на VPS

```bash
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

    sudo dpkg -i cloudflared-linux-amd64.deb

    cloudflared --version
```

# 5. Логин

```bash
    cloudflared login
```

Убедится что создан файл с секретами типа xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.json
по пути /etc/cloudflared

# 6. Создать конфигурацию туннеля /etc/cloudflared/config.yml

Указать свой ИД в полях tunnel и credentials-file
Ид это имя файла созданного после логина - xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Выполнить валидацию конфига

```bash
    cloudflared tunnel ingress validate
```

# 7. Создать туннель

```bash
    cloudflared tunnel create radio-tunnel

    cloudflared tunnel list

    cloudflared tunnel info radio-tunnel
```

# 8. Запуск службы

```bash
    sudo cloudflared service install

    sudo systemctl enable cloudflared

    sudo systemctl start cloudflared

    sudo systemctl status cloudflared
```

При изменении /etc/cloudflared/config.yml выполнить рестарт службы

```bash
    cloudflared tunnel ingress validate

    sudo systemctl restart cloudflared

    sudo systemctl status cloudflared
```

Для просмотра логов

```bash
    journalctl -u cloudflared -e -f
```

# 9. Остановка и удаление

```bash
    sudo systemctl stop cloudflared

    sudo systemctl disable cloudflared

    sudo systemctl status cloudflared

    sudo cloudflared service uninstall

    cloudflared tunnel delete radio-tunnel

    cloudflared tunnel cleanup radio-tunnel

    sudo apt remove --purge cloudflared -y

    sudo rm -rf /etc/cloudflared

    sudo rm -rf ~/.cloudflared
```
