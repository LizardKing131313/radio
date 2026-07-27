## Why

The audio cache and PostgreSQL backups are production data with finite disk space, but their retention behavior is not
defined as an explicit, testable lifecycle. The next production maintenance change should prevent unbounded growth
without deleting audio still needed by the catalog, queue, or current broadcast.

## What Changes

- Add a retention capability for selecting removable cold-cache audio and old PostgreSQL backup files.
- Protect files referenced by active catalog tracks, queued playback, and the currently playing track.
- Add dry-run reporting before deletion and make deletion decisions deterministic and testable.
- Reuse the existing cache paths, PostgreSQL metadata, and backup directory; do not add a service or database schema.
- Keep existing hot-cache limits and prefetch blacklist behavior unchanged.
- Document and test backup retention and cleanup failure handling.

## Capabilities

### New Capabilities

- `retention-lifecycle`: Safe, observable retention decisions for audio cache and PostgreSQL backup artifacts.

### Modified Capabilities

- `prefetch-cache`: Define how retention protects audio files referenced by active runtime state while enforcing cache
  cleanup.
- `data-persistence`: Define retention expectations for filesystem PostgreSQL backup artifacts without moving domain
  state out of PostgreSQL.
- `deployment`: Run production retention automatically as a Kubernetes-managed maintenance job.

## Impact

- Affected code: cache maintenance helpers, backup cleanup integration, configuration, and focused unit tests.
- Affected operations: a dry-run and deletion command or job will report removed, protected, and failed artifacts.
- No API, queue, Liquidsoap, Kubernetes topology, or database schema changes are expected.
- Validation: focused retention tests, OpenSpec strict validation, `make ci`, rendered deployment validation, and a
  production-like dry-run followed by disk-space verification.
