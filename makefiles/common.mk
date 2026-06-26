# ---- Shared paths ------------------------------------------------------------
MAKEFILES_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ROOT_DIR      := $(abspath $(MAKEFILES_DIR)/..)
VENV_DIR      ?= $(ROOT_DIR)/.venv

# ---- OS-aware venv layout ----------------------------------------------------
ifeq ($(OS),Windows_NT)
VENV_BIN := $(VENV_DIR)/Scripts
PY       := python
NULLDEV  := NUL
NPM      ?= npm.cmd
NPX      ?= npx.cmd
else
VENV_BIN := $(VENV_DIR)/bin
PY       := python3
NULLDEV  := /dev/null
NPM      ?= npm
NPX      ?= npx
endif

PIP      := $(VENV_BIN)/pip
PYTHON   := $(VENV_BIN)/python

# Tools inside venv (не вызываем activate)
PIP_COMPILE := $(VENV_BIN)/pip-compile
PIP_SYNC    := $(VENV_BIN)/pip-sync

# Проектные пути/утилиты
RUFF     := $(VENV_BIN)/ruff
BLACK    := $(VENV_BIN)/black
MYPY     := $(VENV_BIN)/mypy
PYTEST   := $(VENV_BIN)/pytest
OPENSPEC ?= $(NPX) --yes @fission-ai/openspec@1.4.1

# Python source roots. Tooling must not walk virtualenvs/caches via ".".
PY_CODE_DIRS := alembic manager scripts tests
FRONTEND_DIR := $(ROOT_DIR)/frontend
