## 1. Tests First

- [x] 1.1 Add unit tests for deterministic cold-cache candidate selection, oldest-first ordering, quota handling, and
  protection of active, queued, and currently playing track references.
- [x] 1.2 Add unit tests proving dry-run produces a report without deleting files and records deletion failures.
- [x] 1.3 Add unit tests for backup filename filtering, newest-N retention, unrelated-file protection, and failed dump
  deletion.

## 2. Retention Decisions

- [x] 2.1 Implement pure retention decision helpers for audio and PostgreSQL backup artifacts with explicit protected
  paths and deterministic reports.
- [x] 2.2 Reuse the existing prefetch cache maintenance path and extend it so protected audio cannot be removed by quota
  or hot-cache cleanup.
- [x] 2.3 Add the smallest configuration and command/job entry point needed to run audio and backup retention in dry-run
  or delete mode without adding an API endpoint.
- [x] 2.4 Add a Kubernetes CronJob that invokes delete mode automatically after the daily backup.

## 3. Runtime Integration

- [x] 3.1 Load protected audio references from existing PostgreSQL track and playback state without adding schema
  changes.
- [x] 3.2 Integrate backup retention with the existing PostgreSQL backup location and report cleanup results through
  operator-visible logs.
- [x] 3.3 Validate a production-like dry-run against cache and backup fixtures, then verify free disk space and retained
  playable files.
- [x] 3.4 Validate scheduled retention manifests and the PostgreSQL network policy path.

## 4. Validation

- [x] 4.1 Run `openspec validate --all --strict --no-interactive`.
- [x] 4.2 Run the CI gate and resolve lint, typecheck, formatting, or test failures.
- [x] 4.3 Run `kubectl kustomize deploy` and document the controlled deployment and rollback checks.

## Validation Notes

- OpenSpec strict validation: 18/18 passed.
- Python gate: ruff, black, mypy, and 111 tests passed (1 skipped).
- `kubectl kustomize deploy`: passed.
- Full CI gate passed when its component commands were run from PowerShell: Python and frontend checks all passed.
- The `make ci` wrapper itself is not runnable from this Windows shell because it maps the workspace to `/c/Work/radio`
  and invokes WSL, where that path is unavailable.
- Retention CronJob render and PostgreSQL ingress policy validation: passed.
