#!/usr/bin/env bash
# Готовит WSL Ubuntu для Ansible, ставит ansible в venv и тянет Galaxy коллекции из ansible/requirements.yml
#
# Запуск:
# chmod +x bootstrap_wsl_ansible.sh
# bash bootstrap_wsl_ansible.sh
set -euo pipefail

# ---------- настройки ----------
PROJECT_ROOT="$(pwd)"                          # запускай из корня проекта
VENV_DIR="${PROJECT_ROOT}/.venv-wsl"           # отдельное окружение для WSL
GALAXY_REQ="${PROJECT_ROOT}/ansible/requirements.yml"
APT_PACKAGES=(
  python3-venv python3-pip git openssh-client sshpass dos2unix
  build-essential libssl-dev libffi-dev python3-dev
)
PIP_PACKAGES=(
  "ansible>=9" ansible-lint paramiko
)
# -------------------------------

echo "==> Проект: ${PROJECT_ROOT}"
echo "==> Проверяю интернет и DNS…"
if ! getent hosts archive.ubuntu.com >/dev/null 2>&1; then
  echo "!! DNS не резолвит archive.ubuntu.com. Если недавно чинил WSL, перезапусти через PowerShell:  wsl --shutdown"
  echo "Продолжаю попытку, но apt может залипнуть."
fi

echo "==> Обновляю и ставлю пакеты: ${APT_PACKAGES[*]}"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"

echo "==> Создаю виртуальное окружение: ${VENV_DIR}"
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "==> Обновляю pip и ставлю: ${PIP_PACKAGES[*]}"
python -m pip install --upgrade pip
python -m pip install "${PIP_PACKAGES[@]}"

echo "==> Ansible версия:"
ansible --version || true

if [[ -f "${GALAXY_REQ}" ]]; then
  echo "==> Найден ${GALAXY_REQ}. Устанавливаю коллекции из Galaxy…"
  # Коллекции по умолчанию ставятся в ~/.ansible/collections
  ansible-galaxy collection install -r "${GALAXY_REQ}"
else
  echo "==> Файл ${GALAXY_REQ} не найден. Шаг Galaxy пропущен (это ок)."
fi

echo "==> Немного качества жизни: git не будет портить переносы строк"
git config --global core.autocrlf input || true

echo "==> Готово. Дальше по чеклисту:"
echo "   1) Активировать окружение при новой сессии:"
echo "        source .venv-wsl/bin/activate"
echo "   2) Проверить SSH доступ к VPS: ssh user@VPS_IP"
echo "   3) cd ansible"
echo "   3) Если в ansible.cfg прописан inventory (hosts.ini, hosts.local.ini) и vault_password_file:"
echo "      - Проверка связи:"
echo "          ansible all -m ping"
echo "      - Запуск плейбука:"
echo "          ansible-playbook site.yml"
echo "   4) При ошибке Ansible is being run in a world writable directory выполнить:"
echo "          sudo nano /etc/wsl.conf"
echo "          [automount]
                options = \"metadata,umask=022,fmask=0111\""
echo "      В PowerShell:"
echo "          wsl --shutdown"
echo
echo "WSL готов"
