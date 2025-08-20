# ===== Ansible Makefile fragment =====
# Использование: под WSL запускай `make -f Makefile` в корне проекта,
# предварительно подключив этот файл: `include makefiles/ansible.mk`

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

# --- Настройки по умолчанию (можно переопределять в верхнем Makefile или через CLI) ---
VENV           ?= .venv-wsl
PYTHON_BIN     ?= python3
PIP_BIN        ?= pip
PLAYBOOK       ?= ansible/site.yml
INVENTORY      ?= ansible/hosts.ini,ansible/hosts.local.ini
GALAXY_REQ     ?= ansible/requirements.yml
ANSIBLE_CFG    ?= ansible/ansible.cfg
VAULT_FILE     ?= ansible/group_vars/all/vault.yml

# --- Вспомогательные шорткаты ---
ACTIVATE := source $(VENV)/bin/activate
AI := ANSIBLE_CONFIG=$(ANSIBLE_CFG) ansible
AIPB := ANSIBLE_CONFIG=$(ANSIBLE_CFG) ansible-playbook
AIG := ANSIBLE_CONFIG=$(ANSIBLE_CFG) ansible-galaxy

# ===== HELP =====
help-ansible: ## Показать хелп по целям Ansible
	@echo "Ansible targets:"
	@awk 'BEGIN{FS":.*##"; printf "\n  %-28s %s\n\n", "Цель", "Описание"} /^[a-zA-Z0-9_.-]+:.*##/{printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | grep -E 'ansible\.|help-ansible|^  Цель|^$$'

# ===== Bootstrap / окружение =====
ansible.init: ## Установить базовые пакеты (apt), создать venv и поставить ansible + ansible-lint
	@echo "==> APT: base utils"
	sudo apt-get update -y
	sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip git openssh-client dos2unix build-essential libssl-dev libffi-dev python3-dev
	@echo "==> Python venv: $(VENV)"
	@if [[ ! -d "$(VENV)" ]]; then $(PYTHON_BIN) -m venv "$(VENV)"; fi
	@echo "==> pip upgrade & install ansible"
	@$(ACTIVATE); $(PYTHON_BIN) -m $(PIP_BIN) install --upgrade pip
	@$(ACTIVATE); $(PYTHON_BIN) -m $(PIP_BIN) install "ansible>=9" ansible-lint
	@$(ACTIVATE); $(AI) --version || true
	@echo "==> Done."

ansible.upgrade: ## Обновить ansible и ansible-lint в venv
	@$(ACTIVATE); $(PYTHON_BIN) -m $(PIP_BIN) install --upgrade "ansible>=9" ansible-lint
	@$(ACTIVATE); $(AI) --version

# ===== Galaxy =====
ansible.galaxy: ## Установить коллекции из ansible/requirements.yml (если файл существует)
	@if [[ -f "$(GALAXY_REQ)" ]]; then \
		echo "==> Installing Galaxy collections from $(GALAXY_REQ)"; \
		$(ACTIVATE); $(AIG) collection install -r "$(GALAXY_REQ)"; \
	else \
		echo "==> $(GALAXY_REQ) not found. Skip."; \
	fi

# ===== Проверки и запуск =====
ansible.ping: ## ansible -m ping для всех хостов
	@$(ACTIVATE); $(AI) -i $(INVENTORY) all -m ping

ansible.lint: ## ansible-lint для плейбуков/ролей
	@$(ACTIVATE); ansible-lint -c "$(ANSIBLE_CFG)" || ansible-lint || true

ansible.check: ## Прогон плейбука в --check (dry-run)
	@$(ACTIVATE); $(AIPB) -i $(INVENTORY) "$(PLAYBOOK)" --check $(LIMIT) $(TAGS) $(EXTRA_VARS)

ansible.run: ## Запуск плейбука (боевой)
	@$(ACTIVATE); $(AIPB) -i $(INVENTORY) "$(PLAYBOOK)" $(LIMIT) $(TAGS) $(EXTRA_VARS)

ansible.tags: ## Показать доступные теги плейбука
	@$(ACTIVATE); $(AIPB) -i $(INVENTORY) "$(PLAYBOOK)" --list-tags

ansible.tasks: ## Показать задачи и роли (outline)
	@$(ACTIVATE); $(AIPB) -i $(INVENTORY) "$(PLAYBOOK)" --list-tasks

# ===== Vault =====
# VARS:
#   FILE=<путь к vault.yml> (по умолчанию $(VAULT_FILE))
#   KEY=<имя_переменной> VALUE=<значение>  — для ansible.vault.add
FILE ?= $(VAULT_FILE)

ansible.vault.encrypt: ## Зашифровать FILE (vault.yml) целиком
	@test -f "$(FILE)" || (echo "File not found: $(FILE)"; exit 1)
	@$(ACTIVATE); ansible-vault encrypt "$(FILE)"

ansible.vault.decrypt: ## Расшифровать FILE целиком (осторожно!)
	@test -f "$(FILE)" || (echo "File not found: $(FILE)"; exit 1)
	@$(ACTIVATE); ansible-vault decrypt "$(FILE)"

ansible.vault.edit: ## Открыть FILE в редакторе (ansible-vault edit)
	@test -f "$(FILE)" || (echo "File not found: $(FILE)"; exit 1)
	@$(ACTIVATE); ansible-vault edit "$(FILE)"

ansible.vault.view: ## Показать FILE (ansible-vault view)
	@test -f "$(FILE)" || (echo "File not found: $(FILE)"; exit 1)
	@$(ACTIVATE); ansible-vault view "$(FILE)"

ansible.vault.add: ## Добавить строковый секрет: KEY=var_name VALUE=secret [FILE=...]
	@test -n "$(KEY)" || (echo "Set KEY=var_name"; exit 1)
	@test -n "$(VALUE)" || (echo "Set VALUE=secret"; exit 1)
	@mkdir -p "$$(dirname "$(FILE)")"
	@touch "$(FILE)"
	@echo "==> Append encrypted $(KEY) to $(FILE)"
	@$(ACTIVATE); ansible-vault encrypt_string '$(VALUE)' --name '$(KEY)' >> "$(FILE)"

# ===== Примеры =====
# make ansible.run TAGS='-t users,deploy' LIMIT='-l vps-radio'
# make ansible.check EXTRA_VARS='-e app_env=prod'
# make ansible.vault.add KEY=youtube_api_key VALUE='AIza...'
# make ansible.ssh HOST=1.2.3.4 USER=root
