include $(dir $(lastword $(MAKEFILE_LIST)))common.mk

# ---- Helpers -----------------------------------------------------------------
.PHONY: help-setup
help-setup:
	@echo "Targets:"
	@echo "  venv            - create virtualenv (.venv)"
	@echo "  upgrade-pip     - upgrade pip/setuptools/wheel"
	@echo "  pip-tools       - install pip-tools (pip-compile, pip-sync)"
	@echo "  setup           - venv + upgrade + pip-tools + editable '.[dev]' + pre-commit install"
	@echo "  hooks           - reapply pre-commit hooks if config .pre-commit-config.yaml was changed"
	@echo "  compile         - compile requirements.txt"
	@echo "  compile-dev     - compile requirements-dev.txt"
	@echo "  compile-all     - compile requirements-all.txt"
	@echo "  compile-every   - compile all requirements files"
	@echo "  compile-update  - update all lock-files (set latest compatible versions)"
	@echo "  sync            - pip-sync env to requirements.txt"
	@echo "  sync-dev        - pip-sync env to requirements-dev.txt"
	@echo "  sync-all        - pip-sync env to requirements-all.txt"
	@echo "  clean-venv      - remove .venv"

# ---- Venv --------------------------------------------------------------------
VENV_STAMP := $(VENV_DIR)/.stamp

$(VENV_STAMP):  ## stamp-dir to mark venv
	$(PY) -m venv "$(VENV_DIR)"
	@echo "ok" > "$(VENV_STAMP)"

.PHONY: venv
venv: $(VENV_STAMP)

.PHONY: upgrade-pip
upgrade-pip: venv
	$(PYTHON) -m pip install -U pip setuptools wheel

# ---- pip-tools ---------------------------------------------------------------
.PHONY: pip-tools
pip-tools: upgrade-pip
	$(PIP) install -U pip-tools

# ---- Project setup -----------------------------------------------------------
.PHONY: setup
setup: venv upgrade-pip pip-tools
	# editable install if project uses pyproject/setuptools
	@if [ -f "$(ROOT_DIR)/pyproject.toml" ] || [ -f "$(ROOT_DIR)/setup.cfg" ] || [ -f "$(ROOT_DIR)/setup.py" ]; then \
		$(PIP) install -e "$(ROOT_DIR)[dev]" ; \
	else \
		echo "No build metadata found (pyproject.toml/setup.cfg); skipping editable install"; \
	fi
	# pre-commit
	$(PIP) install -U pre-commit
	$(MAKE) -f "$(ROOT_DIR)/makefiles/setup.mk" -C "$(ROOT_DIR)" hooks

.PHONY: hooks
hooks:
	cd "$(ROOT_DIR)" && "$(VENV_BIN)/pre-commit" clean
	cd "$(ROOT_DIR)" && "$(VENV_BIN)/pre-commit" install

# ---- Compile requirements ----------------------------------------------------
.PHONY: compile
compile: pip-tools
	$(PIP_COMPILE) "$(ROOT_DIR)/pyproject.toml" -o "$(ROOT_DIR)/requirements.txt"

.PHONY: compile-dev
compile-dev: pip-tools
	$(PIP_COMPILE) "$(ROOT_DIR)/pyproject.toml" --extra dev -o "$(ROOT_DIR)/requirements-dev.txt"

.PHONY: compile-all
compile-all: pip-tools
	$(PIP_COMPILE) "$(ROOT_DIR)/pyproject.toml" --extra dev -o "$(ROOT_DIR)/requirements-all.txt"

.PHONY: compile-every
compile-every: compile compile-dev compile-all

# ---- Compile requirements update ---------------------------------------------
.PHONY: compile-update
compile-update: compile-every
	$(PIP_COMPILE) -U "$(ROOT_DIR)/pyproject.toml" -o "$(ROOT_DIR)/requirements.txt"
	$(PIP_COMPILE) -U "$(ROOT_DIR)/pyproject.toml" --extra dev -o "$(ROOT_DIR)/requirements-dev.txt"
	$(PIP_COMPILE) -U "$(ROOT_DIR)/pyproject.toml" --extra dev -o "$(ROOT_DIR)/requirements-all.txt"

# ---- Sync (precise env) ------------------------------------------------------
.PHONY: sync
sync: pip-tools
	$(PIP_SYNC) "$(ROOT_DIR)/requirements.txt"

.PHONY: sync-dev
sync-dev: pip-tools
	$(PIP_SYNC) "$(ROOT_DIR)/requirements-dev.txt"

.PHONY: sync-all
sync-all: pip-tools
	$(PIP_SYNC) "$(ROOT_DIR)/requirements-all.txt"

# ---- Clean -------------------------------------------------------------------
.PHONY: clean-venv
clean-venv:
	@echo "Removing .venv ..."
ifeq ($(OS),Windows_NT)
	@if exist "$(VENV_DIR)" rmdir /S /Q "$(VENV_DIR)"
else
	@rm -rf "$(VENV_DIR)"
endif
