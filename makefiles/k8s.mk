include $(dir $(lastword $(MAKEFILE_LIST)))common.mk

# ---- Kubernetes --------------------------------------------------------------
.PHONY: k8s-status
k8s-status:
	kubectl -n radio get pods,svc,ingress,certificate,job,cronjob,pvc

.PHONY: k8s-db
k8s-db:
	kubectl -n radio exec -it postgres-0 -- sh -lc 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.PHONY: k8s-db-forward
k8s-db-forward:
	kubectl -n radio port-forward svc/postgres 15432:5432

.PHONY: k8s-backups
k8s-backups:
	kubectl -n radio exec deploy/radio -c prefetch -- sh -lc 'ls -lh /opt/radio/cache/postgres 2>/dev/null || echo "backups not found yet"'

.PHONY: k8s-backup
k8s-backup:
	kubectl -n radio delete job postgres-backup-manual --ignore-not-found=true
	kubectl -n radio create job --from=cronjob/postgres-backup postgres-backup-manual
	kubectl -n radio wait --for=condition=complete job/postgres-backup-manual --timeout=180s

.PHONY: k8s-restore
k8s-restore:
ifndef DUMP
	$(error Use: make k8s-restore DUMP=./radio.dump)
endif
	kubectl -n radio cp "$(DUMP)" postgres-0:/tmp/radio.dump
	kubectl -n radio exec -it postgres-0 -- sh -lc 'pg_restore --clean --if-exists -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" /tmp/radio.dump'
