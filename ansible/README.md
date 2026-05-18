# VPS deploy

Минимальный путь для чистого Debian/Ubuntu VPS:

```bash
cd /mnt/c/work/radio
cp ansible/inventory/hosts.example.yml ansible/inventory/hosts.local.yml
```

В `hosts.local.yml` укажи IP VPS и `ansible_user: root`.
Если реально надо снести существующего пользователя `radio` вместе с home, временно поставь
`radio_recreate_user: true` в inventory/group_vars.

Перед запуском нужен только YouTube API key:

```bash
export RADIO_YOUTUBE_API_KEY='...'
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
- создает пользователя `radio` и дает ему `kubectl`;
- открывает SSH и `30080/tcp`;
- копирует проект в `/opt/radio/app`;
- собирает `radio-manager:latest` на VPS и импортирует образ в k3s;
- генерирует `deploy/k8s/secret.yaml` на VPS;
- запускает `kubectl apply -k deploy`, Alembic и rollout.

После успешного запуска:

```bash
ssh radio@VPS_IP 'kubectl -n radio get pods,svc'
curl http://VPS_IP:30080/health
```
