## Purpose

Фиксирует инженерные требования к коду в этом репозитории. Этот контракт нужен,
чтобы OpenSpec changes и агентские правки не раздували проект лишним кодом,
конфигами, зависимостями и новыми паттернами без текущей необходимости.

## Requirements

### Requirement: Minimal implementation scope

Code changes MUST implement the current requirement with the smallest readable
set of files, branches, states, and moving parts.

#### Scenario: New behavior is added

- **WHEN** a change introduces new behavior
- **THEN** implementation touches only the modules needed for that behavior
- **AND** unrelated refactors are left out of the change

#### Scenario: Future-only code is proposed

- **WHEN** a helper, class, config field, table, service, or branch has no current caller or test
- **THEN** it is not added until a real requirement needs it

### Requirement: Existing pattern reuse

New code SHALL reuse existing project patterns, module boundaries, helpers, and
test style before introducing a new local pattern.

#### Scenario: API behavior changes

- **WHEN** an endpoint is added or modified
- **THEN** it uses the existing FastAPI dependency, repository, response, and auth patterns
- **AND** business logic stays outside route bodies when a repository or domain helper already fits

#### Scenario: Database behavior changes

- **WHEN** persistent behavior changes
- **THEN** code uses the existing SQLAlchemy repository/session pattern
- **AND** schema changes are represented by Alembic

#### Scenario: Runtime command changes

- **WHEN** a CLI/runtime command changes
- **THEN** it follows the existing small `manager.main` command dispatch style
- **AND** Kubernetes remains responsible for long-running process lifecycle

### Requirement: Configuration discipline

New configuration MUST be added only when the current behavior cannot be derived
from existing config, code, or Kubernetes wiring.

#### Scenario: Runtime option is needed

- **WHEN** a runtime option is genuinely needed
- **THEN** it is added to the existing `AppConfig` shape or Kubernetes ConfigMap/Secret path
- **AND** default behavior remains explicit and documented by tests or specs

#### Scenario: Config would only mirror code

- **WHEN** a proposed config value only exposes an implementation detail without a current operator need
- **THEN** the value stays in code instead of becoming another setting

### Requirement: Dependency discipline

New dependencies MUST be added only when the standard library or existing
project dependencies cannot solve the current problem cleanly.

#### Scenario: External package is proposed

- **WHEN** a change proposes a new package
- **THEN** the design explains the current problem it solves
- **AND** the implementation uses the package in production code or tests immediately

#### Scenario: Existing dependency already fits

- **WHEN** an existing dependency provides the required capability
- **THEN** the change reuses it instead of adding another package with overlapping purpose

### Requirement: Abstraction discipline

New abstractions SHALL be introduced only when they reduce real duplication,
remove meaningful complexity, or match an established local boundary.

#### Scenario: One-off behavior is implemented

- **WHEN** behavior has a single caller and no repeated shape
- **THEN** the code stays local and direct

#### Scenario: Repeated behavior exists

- **WHEN** the same behavior is repeated across modules
- **THEN** extraction is allowed only if it makes call sites shorter and easier to reason about

### Requirement: Small validation surface

Code changes MUST remain covered by the smallest useful validation set for the
risk of the change.

#### Scenario: Pure spec or docs change

- **WHEN** only OpenSpec or documentation changes
- **THEN** `openspec validate --all --strict --no-interactive` and diff hygiene are enough

#### Scenario: Python behavior changes

- **WHEN** Python behavior changes
- **THEN** focused tests are added or updated
- **AND** `make ci` remains the readiness gate
