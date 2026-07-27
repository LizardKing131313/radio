## Context

The prefetch worker already maintains `cache/cold` and `cache/hot`, enforces a byte quota and item limit, and stores
track metadata in PostgreSQL. The backup CronJob writes compressed PostgreSQL dumps under the existing cache volume.
Current cleanup is driven by cache limits but does not have a lifecycle contract that explicitly protects files needed
by playback or previews deletion.

## Goals / Non-Goals

**Goals:**

- Make retention decisions from filesystem candidates plus PostgreSQL references.
- Protect active, queued, and currently playing tracks before deleting cold audio.
- Provide a deterministic dry-run result containing candidates, protected files, and deletions.
- Retain only the configured number or age of PostgreSQL backups and report failed deletions.
- Keep the existing cache layout, repositories, and Kubernetes ownership model.

**Non-Goals:**

- No new database tables, migrations, API endpoints, or external services.
- No change to Liquidsoap rotation, queue semantics, or hot-cache promotion policy.
- No API endpoint or always-on retention worker; automatic deletion is owned by an explicit Kubernetes CronJob.

## Decisions

- Implement pure retention decision helpers that accept filesystem metadata and protected paths, then keep deletion as a
  separate effect. This makes dry-run and deletion share exactly the same selection logic.
- Build the protected audio set from PostgreSQL track paths and queue/current-playback identifiers, resolving paths
  under the configured cache root before comparison. Files outside the cache root are never deleted by this change.
- Use age and/or quota thresholds already represented by configuration, with deterministic oldest-first ordering and
  explicit protection taking precedence over age or quota.
- Keep backup retention file-based: select only recognized dump names, sort by modification time, retain the configured
  newest set, and ignore unrelated files. A failed deletion is reported and does not abort evaluation of other files.
- Prefer a CLI/job entry point over an HTTP endpoint so retention remains an operational filesystem task and does not
  expand the public API surface.
- Run the delete mode from a dedicated Kubernetes CronJob after the daily backup job. Keep `python -m manager retention`
  dry-run available for manual inspection, while the scheduled job uses `--delete` and `concurrencyPolicy: Forbid`.

## Risks / Trade-offs

- [Risk] PostgreSQL metadata can reference a missing file. -> The missing path is reported but does not block cleanup of
  unrelated candidates.
- [Risk] A track can become active between selection and deletion. -> Run cleanup as a single controlled operation,
  re-check protected paths immediately before deletion, and document that live cleanup must not overlap deployment or
  manual queue changes.
- [Risk] Incorrect backup filename matching could remove unrelated files. -> Restrict candidates to the existing dump
  naming pattern and test unrelated files explicitly.

## Migration Plan

1. Add decision and deletion tests using temporary cache and backup directories.
2. Implement dry-run output and deletion behind the existing runtime command/configuration patterns.
3. Run a production-like dry-run and inspect protected/deletable sets.
4. Enable scheduled or manual deletion only after the dry-run is reviewed.
5. Roll back by disabling the retention invocation; no schema or data migration is required.
