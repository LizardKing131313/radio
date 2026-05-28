# VPS deploy

Минимальный путь для чистого Debian/Ubuntu VPS:

```bash
cd /mnt/c/work/radio
cp ansible/inventory/hosts.example.yml ansible/inventory/hosts.local.yml
```

В `hosts.local.yml` укажи IP VPS и `ansible_user: root`.
Если реально надо снести существующего пользователя `radio` вместе с home, временно поставь
`radio_recreate_user: true` в inventory/group_vars.

Если используется второй российский VPS как публичный edge-proxy, добавь его в группу
`vps_edge`. Имя хоста внутри inventory (`radio-vps`, `ru-edge-vps`) - только локальный
алиас Ansible, на DNS оно не влияет.

Перед запуском нужны YouTube API key, домен с A/AAAA-записью на VPS, email для Let's Encrypt
и публичный SSH-ключ в `radio_authorized_key_files` или `radio_authorized_keys`:

```bash
export RADIO_YOUTUBE_API_KEY='...'
export RADIO_DOMAIN='origin-radio.example.com'
export RADIO_TLS_EMAIL='admin@example.com'
```

Для схемы с российским edge нужен отдельный публичный домен edge, который смотрит на
российский VPS. Origin-домен должен смотреть на иностранный VPS, потому что по нему
работают ingress-nginx и cert-manager внутри k3s:

```bash
export RADIO_EDGE_DOMAIN='radio.example.com'
export RADIO_EDGE_TLS_EMAIL="$RADIO_TLS_EMAIL"
# Обычно не нужно: по умолчанию edge ходит на https://$RADIO_DOMAIN
export RADIO_EDGE_ORIGIN_HOST="$RADIO_DOMAIN"
export RADIO_EDGE_ORIGIN_URL="https://$RADIO_DOMAIN"
```

`RADIO_POSTGRES_PASSWORD` и `RADIO_ADMIN_TOKEN` можно не задавать. Тогда Ansible создаст их локально в
`ansible/.generated/`, эта директория игнорируется git.

Запуск из WSL:

```bash
make -f Makefile -f makefiles/ansible.mk ansible.init
make -f Makefile -f makefiles/ansible.mk ansible.galaxy
make -f Makefile -f makefiles/ansible.mk ansible.run INVENTORY=ansible/inventory/hosts.local.yml
```

Что делает playbook:

- ставит базовые пакеты, Docker и k3s;
- создает пользователя `radio` без passwordless sudo;
- включает SSH hardening, fail2ban и k3s secrets encryption;
- ставит cert-manager и ingress-nginx внутри k3s;
- выпускает Let's Encrypt сертификат через Kubernetes Ingress;
- открывает SSH, `80/tcp` и `443/tcp`;
- копирует проект в `/opt/radio/app`;
- собирает `radio-manager:latest` на VPS и импортирует образ в k3s;
- генерирует `deploy/k8s/secret.yaml`, `issuer.yaml` и `ingress.yaml` на VPS;
- запускает `kubectl apply -k deploy`, Alembic и rollout.

Для группы `vps_edge` playbook отдельно:

- ставит host nginx, certbot, ufw и fail2ban;
- выпускает отдельный Let's Encrypt сертификат для `RADIO_EDGE_DOMAIN`;
- проксирует трафик на origin по HTTPS с проверкой сертификата upstream;
- передает на origin `Host: RADIO_EDGE_ORIGIN_HOST`, чтобы сработал Kubernetes Ingress;
- не кеширует live-playlist `.m3u8`, но коротко кеширует HLS-сегменты `.ts/.m4s/.mp4`;
- включает автообновление сертификата через `certbot.timer`.

После успешного запуска:

```bash
ssh root@VPS_IP 'k3s kubectl -n radio get pods,svc,ingress,certificate'
curl https://radio.example.com/health
```

Если origin уже запущен и нужно настроить только российский edge:

```bash
make -f Makefile -f makefiles/ansible.mk ansible.run \
  INVENTORY=ansible/inventory/hosts.local.yml LIMIT='--limit vps_edge'
```

По умолчанию `radio` не получает cluster-admin kubeconfig. Если нужен `kubectl` из-под этого пользователя, поставь
`radio_install_kubeconfig: true`, но это фактически админ-доступ к кластеру.
