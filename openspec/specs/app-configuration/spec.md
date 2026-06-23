## Purpose

Фиксирует поведение конфигурационного слоя приложения. Runtime config читается
из YAML, а секреты и DSN накладываются из env явно перечисленными именами.

## Requirements

### Requirement: YAML configuration loading

Система SHALL читать структурный runtime config из явного YAML path или из
дефолтных путей `data/config.yaml` и `/opt/radio/data/config.yaml`.

#### Scenario: YAML file exists

- **WHEN** config YAML найден
- **THEN** приложение валидирует root как mapping
- **AND** значения накладываются на дефолты `AppConfig`

#### Scenario: YAML file is missing

- **WHEN** config YAML не найден
- **THEN** приложение использует дефолтные значения `AppConfig`
- **AND** импорт модулей не падает из-за отсутствующих секретов

### Requirement: Explicit environment secrets

Система MUST читать секреты и database DSN только из явно поддержанных env
переменных.

#### Scenario: YouTube key is set

- **WHEN** `RADIO_YOUTUBE_API_KEY` или `YOUTUBE_API_KEY` задан
- **THEN** `config.secrets.youtube_api_key` возвращает этот секрет

#### Scenario: Admin token is set

- **WHEN** `RADIO_ADMIN_TOKEN` или `ADMIN_TOKEN` задан
- **THEN** admin API может проверить bearer token

#### Scenario: Database DSN is set

- **WHEN** `RADIO_DATABASE_DSN`, `DATABASE_URL` или `POSTGRES_DSN` задан
- **THEN** database layer использует этот DSN для SQLAlchemy engine

### Requirement: Lazy missing-secret validation

Система SHALL падать на отсутствующих критичных секретах только в момент
реального доступа к конкретному секрету.

#### Scenario: Search worker needs YouTube key

- **WHEN** search worker обращается к `youtube_api_key`
- **THEN** отсутствие ключа вызывает `MissingConfigError`

#### Scenario: Non-search code imports config

- **WHEN** тест или команда не использует YouTube API key
- **THEN** отсутствие ключа не ломает импорт и создание базового config object

### Requirement: HLS settings stay explicit

HLS settings MUST приходить из YAML/defaults, а не из скрытых env overrides.

#### Scenario: Bitrates configured in YAML

- **WHEN** YAML задает список `hls.bitrates`
- **THEN** FFmpeg args используют именно этот список variant bitrate values

#### Scenario: Env contains unrelated HLS values

- **WHEN** env содержит случайные HLS-похожие переменные
- **THEN** `AppConfig` не меняет HLS config через неявный binding
