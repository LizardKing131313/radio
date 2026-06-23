include $(dir $(lastword $(MAKEFILE_LIST)))common.mk

# ---- Helpers -----------------------------------------------------------------
.PHONY: help-dev
help-dev:
	@echo "Targets:"
	@echo "  lint 					 - check code files with configuration from pyproject.toml"
	@echo "  format  				 - check and auto fix code files with configuration from pyproject.toml"
	@echo "  typecheck  		 - mypy type checks with configuration from pyproject.toml"
	@echo "  test  					 - run pytest. Stop after first failed test"
	@echo "  test-all  			 - run all pytest"
	@echo "  coverage  			 - run all pytest with coverage"
	@echo "  coverage-badge  - generate coverage badge"
	@echo "  ci  						 - run linter and tests"

# ---- DEV ---------------------------------------------------------------------
.PHONY: lint
lint:
	cd "$(ROOT_DIR)" && "$(RUFF)" check .
	cd "$(ROOT_DIR)" && "$(BLACK)" --check .

.PHONY: format
format:
	cd "$(ROOT_DIR)" && "$(RUFF)" check . --fix
	cd "$(ROOT_DIR)" && "$(BLACK)" .

.PHONY: typecheck
typecheck:
	cd "$(ROOT_DIR)" && "$(MYPY)" .

.PHONY: test
test:
	cd "$(ROOT_DIR)" && "$(PYTEST)" --maxfail=1 -q --disable-warnings

.PHONY: test-all
test-all:
	cd "$(ROOT_DIR)" && "$(PYTEST)" -q --disable-warnings

.PHONY: coverage
coverage:
	cd "$(ROOT_DIR)" && "$(PYTEST)" -q --disable-warnings --cov=. --cov-report=term-missing --cov-report=xml --cov-report=html

.PHONY: coverage-badge
coverage-badge:
	cd "$(ROOT_DIR)" && "$(PYTHON)" scripts/badge/gen_badge.py

.PHONY: ci
ci: lint test
