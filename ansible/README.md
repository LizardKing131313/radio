# VPS deploy

Минимальный путь для чистого Debian/Ubuntu VPS:

```bash
cd /mnt/c/work/radio
cp ansible/inventory/hosts.example.yml ansible/inventory/hosts.local.yml
```

В `hosts.local.yml` укажи IP VPS и `ansible_user: root`.
Если реально надо снести существующего пользователя `radio` вместе с home, временно поставь
`radio_recreate_user: true` в inventory/group_vars.

Перед запуском нужны YouTube API key, домен с A/AAAA-записью на VPS, email для Let's Encrypt
и публичный SSH-ключ в `radio_authorized_key_files` или `radio_authorized_keys`:

```bash
export RADIO_YOUTUBE_API_KEY='...'
export RADIO_DOMAIN='radio.example.com'
export RADIO_TLS_EMAIL='admin@example.com'
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

После успешного запуска:

```bash
ssh root@VPS_IP 'k3s kubectl -n radio get pods,svc,ingress,certificate'
curl https://radio.example.com/health
```

По умолчанию `radio` не получает cluster-admin kubeconfig. Если нужен `kubectl` из-под этого пользователя, поставь
`radio_install_kubeconfig: true`, но это фактически админ-доступ к кластеру.
