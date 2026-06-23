## Purpose

Фиксирует минимальный telnet control surface для Liquidsoap. API и queue-player
используют этот слой для request.queue, skip и introspection команд.

## Requirements

### Requirement: Telnet command execution

Система SHALL отправлять одну Liquidsoap telnet command на TCP connection и
читать ответ до `END`.

#### Scenario: Command returns body

- **WHEN** Liquidsoap отвечает body и terminator `END`
- **THEN** client возвращает body без terminator

#### Scenario: Connection fails

- **WHEN** socket connection или read падает
- **THEN** client raises `LiquidsoapTelnetError`

### Requirement: Liquidsoap error handling

Система MUST превращать telnet responses starting with `ERROR:` into
`LiquidsoapTelnetError`.

#### Scenario: Liquidsoap rejects command

- **WHEN** telnet response body начинается с `ERROR:`
- **THEN** caller получает `LiquidsoapTelnetError`
- **AND** API может вернуть `503 Service Unavailable`

### Requirement: Request queue commands

Система SHALL expose typed methods for request queue push, flush, skip, and
queue inspection.

#### Scenario: Queue item is pushed

- **WHEN** queue-player calls `push_request(uri)`
- **THEN** client sends `request_queue.push <uri>`

#### Scenario: Direct play replaces queue

- **WHEN** admin starts a track immediately
- **THEN** API can flush request queue, push direct annotated URI, and skip output

#### Scenario: Lost queued item is checked

- **WHEN** queue-player needs to know whether Liquidsoap still has queued requests
- **THEN** client sends `request_queue.queue`
