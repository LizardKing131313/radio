include $(dir $(lastword $(MAKEFILE_LIST)))common.mk

# ---- Helpers -----------------------------------------------------------------
.PHONY: help-dev
help-dev:
	@echo "Targets:"
	@echo "  lint 					 - check code files with configuration from pyproject.toml"
	@echo "  format  				 - check and auto fix code files with configuration from pyproject.toml"
	@echo "  typecheck  		 - mypy type checks with configuration from pyproject.toml"
	@echo "  spec            - validate OpenSpec specs and active changes"
	@echo "  test  					 - run pytest. Stop after first failed test"
	@echo "  test-all  			 - run all pytest"
	@echo "  coverage  			 - run all pytest with coverage"
	@echo "  coverage-badge  - generate coverage badge"
	@echo "  ci  						 - run specs, linter, typecheck and tests"

# ---- DEV ---------------------------------------------------------------------
.PHONY: lint
lint:
	cd "$(ROOT_DIR)" && "$(RUFF)" check $(PY_CODE_DIRS)
	cd "$(ROOT_DIR)" && "$(BLACK)" --check $(PY_CODE_DIRS)

.PHONY: format
format:
	cd "$(ROOT_DIR)" && "$(RUFF)" check $(PY_CODE_DIRS) --fix
	cd "$(ROOT_DIR)" && "$(BLACK)" $(PY_CODE_DIRS)

.PHONY: typecheck
typecheck:
	cd "$(ROOT_DIR)" && "$(MYPY)" $(PY_CODE_DIRS)

.PHONY: spec
spec:
	cd "$(ROOT_DIR)" && openspec validate --all --strict --no-interactive

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
ci: spec lint typecheck test
