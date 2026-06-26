include $(dir $(lastword $(MAKEFILE_LIST)))common.mk

# ---- Kubernetes --------------------------------------------------------------
K8S_NAMESPACE ?= radio
K8S_DEPLOYMENT ?= radio
K8S_APPLY_PATH ?= deploy
KUBECTL ?= kubectl

RADIO_IMAGE ?= radio-manager:latest
RADIO_IMAGE_TAR ?= $(ROOT_DIR)/.tmp/radio-manager.tar

RADIO_HTTP_PORT ?= 30080
RADIO_API_PORT ?= 18000
RADIO_DB_PORT ?= 15432

.PHONY: k8s-build
k8s-build:
	docker build -t "$(RADIO_IMAGE)" -f docker/app/Dockerfile .

.PHONY: k8s-save
k8s-save:
	$(PY) -c "from pathlib import Path; Path(r'$(RADIO_IMAGE_TAR)').parent.mkdir(parents=True, exist_ok=True)"
	docker save "$(RADIO_IMAGE)" -o "$(RADIO_IMAGE_TAR)"

.PHONY: k8s-import
k8s-import:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -File "$(MAKEFILES_DIR)/k8s-import-image.ps1" -ImageTar "$(RADIO_IMAGE_TAR)" -Kubectl "$(KUBECTL)"
else
	sudo k3s ctr images import "$(RADIO_IMAGE_TAR)"
endif

.PHONY: k8s-apply
k8s-apply:
	$(KUBECTL) apply -k "$(K8S_APPLY_PATH)"

.PHONY: k8s-restart
k8s-restart:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" rollout restart deployment/"$(K8S_DEPLOYMENT)"

.PHONY: k8s-rollout
k8s-rollout:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" rollout status deployment/"$(K8S_DEPLOYMENT)" --timeout=300s

.PHONY: k8s-deploy
k8s-deploy:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" delete job alembic --ignore-not-found=true
	$(KUBECTL) apply -k "$(K8S_APPLY_PATH)"
	$(KUBECTL) -n "$(K8S_NAMESPACE)" wait --for=condition=complete job/alembic --timeout=180s
	$(KUBECTL) -n "$(K8S_NAMESPACE)" rollout restart deployment/"$(K8S_DEPLOYMENT)"
	$(KUBECTL) -n "$(K8S_NAMESPACE)" rollout status deployment/"$(K8S_DEPLOYMENT)" --timeout=300s

.PHONY: k8s-local-release
k8s-local-release:
	$(MAKE) -C "$(ROOT_DIR)" k8s-build
	$(MAKE) -C "$(ROOT_DIR)" k8s-save
	$(MAKE) -C "$(ROOT_DIR)" k8s-import
	$(MAKE) -C "$(ROOT_DIR)" k8s-deploy

.PHONY: k8s-smoke
k8s-smoke: k8s-smoke-web

.PHONY: k8s-smoke-web
k8s-smoke-web:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" exec deploy/"$(K8S_DEPLOYMENT)" -c nginx -- sh -ec 'wget -qO- http://127.0.0.1:8080/player | grep -q "data-radio-app=\"player\""; wget -qO- http://127.0.0.1:8080/admin | grep -q "data-radio-app=\"admin\""; wget -qO- http://127.0.0.1:8080/api/current | grep -q "now_playing"; wget -qO- http://127.0.0.1:8080/manifest.webmanifest | grep -q "start_url"; wget -qO- http://127.0.0.1:8080/sw.js | grep -q "/hls/"; echo "k8s web smoke OK"'

.PHONY: k8s-status
k8s-status:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" get pods,svc,ingress,certificate,job,cronjob,pvc

.PHONY: k8s-db
k8s-db:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" exec -it postgres-0 -- sh -lc 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.PHONY: k8s-forward
k8s-forward: k8s-forward-http

.PHONY: k8s-forward-http
k8s-forward-http:
	@echo "HTTP/player/admin/API/HLS: http://127.0.0.1:$(RADIO_HTTP_PORT)"
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward svc/radio "$(RADIO_HTTP_PORT):80"

.PHONY: k8s-forward-api
k8s-forward-api:
	@echo "Direct FastAPI: http://127.0.0.1:$(RADIO_API_PORT)"
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward deployment/"$(K8S_DEPLOYMENT)" "$(RADIO_API_PORT):8000"

.PHONY: k8s-db-forward
k8s-db-forward: k8s-forward-db

.PHONY: k8s-forward-db
k8s-forward-db:
	@echo "PostgreSQL: 127.0.0.1:$(RADIO_DB_PORT)"
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward svc/postgres "$(RADIO_DB_PORT):5432"

.PHONY: k8s-forward-all
k8s-forward-all:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "\$$ErrorActionPreference = 'Stop'; \$$jobs = @(Start-Job -ScriptBlock { $(KUBECTL) -n '$(K8S_NAMESPACE)' port-forward svc/radio '$(RADIO_HTTP_PORT):80' }; Start-Job -ScriptBlock { $(KUBECTL) -n '$(K8S_NAMESPACE)' port-forward deployment/'$(K8S_DEPLOYMENT)' '$(RADIO_API_PORT):8000' }; Start-Job -ScriptBlock { $(KUBECTL) -n '$(K8S_NAMESPACE)' port-forward svc/postgres '$(RADIO_DB_PORT):5432' }); Write-Host 'HTTP/player/admin/API/HLS: http://127.0.0.1:$(RADIO_HTTP_PORT)'; Write-Host 'Direct FastAPI: http://127.0.0.1:$(RADIO_API_PORT)'; Write-Host 'PostgreSQL: 127.0.0.1:$(RADIO_DB_PORT)'; try { Receive-Job -Job \$$jobs -Wait } finally { Stop-Job -Job \$$jobs -ErrorAction SilentlyContinue; Remove-Job -Job \$$jobs -Force -ErrorAction SilentlyContinue }"
else
	@echo "HTTP/player/admin/API/HLS: http://127.0.0.1:$(RADIO_HTTP_PORT)"
	@echo "Direct FastAPI: http://127.0.0.1:$(RADIO_API_PORT)"
	@echo "PostgreSQL: 127.0.0.1:$(RADIO_DB_PORT)"
	@trap 'kill 0' INT TERM EXIT; \
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward svc/radio "$(RADIO_HTTP_PORT):80" & \
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward deployment/"$(K8S_DEPLOYMENT)" "$(RADIO_API_PORT):8000" & \
	$(KUBECTL) -n "$(K8S_NAMESPACE)" port-forward svc/postgres "$(RADIO_DB_PORT):5432" & \
	wait
endif

.PHONY: k8s-backups
k8s-backups:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" exec deploy/"$(K8S_DEPLOYMENT)" -c prefetch -- sh -lc 'ls -lh /opt/radio/cache/postgres 2>/dev/null || echo "backups not found yet"'

.PHONY: k8s-backup
k8s-backup:
	$(KUBECTL) -n "$(K8S_NAMESPACE)" delete job postgres-backup-manual --ignore-not-found=true
	$(KUBECTL) -n "$(K8S_NAMESPACE)" create job --from=cronjob/postgres-backup postgres-backup-manual
	$(KUBECTL) -n "$(K8S_NAMESPACE)" wait --for=condition=complete job/postgres-backup-manual --timeout=180s

.PHONY: k8s-restore
k8s-restore:
ifndef DUMP
	$(error Use: make k8s-restore DUMP=./radio.dump)
endif
	$(KUBECTL) -n "$(K8S_NAMESPACE)" cp "$(DUMP)" postgres-0:/tmp/radio.dump
	$(KUBECTL) -n "$(K8S_NAMESPACE)" exec -it postgres-0 -- sh -lc 'pg_restore --clean --if-exists -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" /tmp/radio.dump'
