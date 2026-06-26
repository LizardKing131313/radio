include makefiles/common.mk
include makefiles/setup.mk
include makefiles/dev.mk
include makefiles/k8s.mk

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  help-setup, help-dev, help-search"
	@echo "  venv, upgrade-pip, pip-tools, setup, hooks"
	@echo "  compile, compile-dev, compile-all, compile-every, compile-update"
	@echo "  sync, sync-dev, sync-all"
	@echo "  lint, format, typecheck, spec, test, test-all, coverage, coverage-badge, ci"
	@echo "  frontend-install, frontend-typecheck, frontend-test, frontend-build, frontend-check"
	@echo "  k8s-build, k8s-save, k8s-import, k8s-deploy, k8s-local-release"
	@echo "  k8s-status, k8s-smoke, k8s-db, k8s-forward-http, k8s-forward-api, k8s-forward-db, k8s-forward-all"
	@echo "  k8s-backups, k8s-backup, k8s-restore DUMP=./radio.dump"
