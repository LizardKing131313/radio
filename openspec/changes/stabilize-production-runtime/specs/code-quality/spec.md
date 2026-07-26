## MODIFIED Requirements

### Requirement: Small validation surface

Code changes MUST remain covered by the smallest useful validation set for the risk of the change. Runtime and
deployment changes MUST include focused checks for the changed command or observable surface in addition to the full CI
gate.

#### Scenario: Pure spec or docs change

- **WHEN** only OpenSpec or documentation changes
- **THEN** `openspec validate --all --strict --no-interactive` and diff hygiene are enough

#### Scenario: Python behavior changes

- **WHEN** Python behavior changes
- **THEN** focused tests are added or updated
- **AND** `make ci` remains the readiness gate

#### Scenario: Production runtime changes

- **WHEN** Docker runtime or Kubernetes behavior changes
- **THEN** the production image/runtime prerequisite and rendered deployment are checked
- **AND** live API, web, and HLS smoke checks are performed when a cluster is available
