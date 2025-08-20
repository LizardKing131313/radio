include makefiles/common.mk
include makefiles/setup.mk
include makefiles/dev.mk
include makefiles/search.mk

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  help-setup, help-dev, help-search"
	@echo "  venv, upgrade-pip, pip-tools, setup, hooks"
	@echo "  compile, compile-dev, compile-all, compile-every, compile-update"
	@echo "  sync, sync-dev, sync-all"
	@echo "  lint, format, typecheck, test, test-all, coverage, coverage-badge, ci"
	@echo "  update, queue, clean"
