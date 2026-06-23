## Purpose

Defines the lightweight engineering workflow for this repository: spec first for
meaningful behavior changes, tests before implementation where behavior is
observable, and automated checks as early as possible.

## Requirements

### Requirement: Spec-first change flow

Meaningful behavior, API, persistence, runtime, or deployment changes SHALL start
from an OpenSpec change before implementation.

#### Scenario: New feature starts

- **WHEN** a developer starts a non-trivial feature or behavior change
- **THEN** they create an OpenSpec change with proposal, spec deltas, design, and tasks
- **AND** implementation starts only after the tasks describe how the change will be validated

#### Scenario: Tiny mechanical edit

- **WHEN** a change is a typo, formatting update, dependency lock refresh, or equally mechanical edit
- **THEN** it may skip a dedicated OpenSpec change
- **AND** existing lint and tests still apply

### Requirement: Test-first implementation

Behavior changes MUST add or update failing tests before production code when
the behavior can be tested locally.

#### Scenario: API behavior changes

- **WHEN** an endpoint response, validation rule, or auth behavior changes
- **THEN** the task list includes an API test update before the implementation task

#### Scenario: Kubernetes manifest changes

- **WHEN** a deployment behavior changes in manifests
- **THEN** the task list includes a manifest validation command such as `kubectl kustomize deploy`

### Requirement: Shift-left validation

The repository SHALL validate specs, lint, formatting, types, and tests before a
change is considered ready.

#### Scenario: Local CI target

- **WHEN** a developer runs `make ci`
- **THEN** OpenSpec validation, lint, typecheck, and tests run in one command

#### Scenario: Pull request validation

- **WHEN** a pull request runs CI
- **THEN** GitHub Actions validates OpenSpec artifacts before running code checks and tests
