# Development Process

This repo uses a lightweight spec-driven workflow for non-trivial changes.

## Tooling

Make targets run OpenSpec through the pinned package by default:

```bash
npx --yes @fission-ai/openspec@1.4.1 validate --all --strict --no-interactive
```

You can also install OpenSpec once on the machine and override the make variable
when you want to use the global binary:

```bash
npm install -g @fission-ai/openspec@1.4.1
openspec init --tools codex
make spec OPENSPEC=openspec
```

Disable OpenSpec telemetry if needed:

```bash
export OPENSPEC_TELEMETRY=0
```

On Windows PowerShell:

```powershell
$env:OPENSPEC_TELEMETRY = "0"
```

## Change Flow

Use OpenSpec for behavior, API, persistence, runtime, deployment, or larger
refactor changes:

```text
/opsx:propose "short description"
/opsx:apply
/opsx:archive
```

Small mechanical edits can skip a dedicated OpenSpec change, but the checks still
apply.

## TDD Rule

For observable behavior changes, update or add tests before production code:

- API behavior: start in `tests/manager/test_api.py` or nearby API tests.
- Queue behavior: start under `tests/manager/track_queue` or `tests/manager/playback`.
- Runtime helpers: start in the matching `tests/manager/**` module.
- Deployment changes: add a manifest validation task such as `kubectl kustomize deploy`.

## Validation

Run the local gate before considering work ready:

```bash
make ci
```

That runs:

- `openspec validate --all --strict --no-interactive`
- `ruff check .`
- `black --check .`
- `mypy .`
- `pytest --maxfail=1 -q --disable-warnings`
