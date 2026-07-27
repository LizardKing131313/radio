## ADDED Requirements

### Requirement: Frontend source boundary

Browser UI source code MUST live in a dedicated frontend area instead of being embedded as large HTML, CSS, or
JavaScript strings inside Python API modules.

#### Scenario: Web UI behavior is added

- **WHEN** player or admin UI behavior is implemented
- **THEN** the source lives in the frontend area
- **AND** Python route modules only serve shell/static responses or JSON APIs

#### Scenario: Inline UI grows in backend code

- **WHEN** a Python module would need a large inline HTML, CSS, or JavaScript block for browser UI
- **THEN** that UI is moved to frontend source or a small template/static file boundary instead

### Requirement: Frontend shared-code discipline

Shared frontend packages SHALL be introduced only for code used by more than one web client or for a stable integration
boundary.

#### Scenario: Player-only behavior is implemented

- **WHEN** behavior is used only by the player app
- **THEN** it stays in the player app source

#### Scenario: Admin and player reuse the same behavior

- **WHEN** admin and player code both use the same API client, formatting, or UI primitive
- **THEN** shared code can be extracted to a frontend package if it makes call sites smaller and clearer

### Requirement: Frontend dependency discipline

Frontend dependencies MUST be limited to packages that are used by production client code, build tooling, or tests in
the current change.

#### Scenario: New frontend package is proposed

- **WHEN** a frontend package is added
- **THEN** the implementation uses it immediately
- **AND** the package solves a current problem that existing project code or browser APIs do not solve cleanly

#### Scenario: Runtime server package is proposed

- **WHEN** a package would require a long-running Node or SSR server in production
- **THEN** it is not added unless a current requirement explicitly needs that production process
