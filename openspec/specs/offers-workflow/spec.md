## Purpose

Фиксирует workflow пользовательских предложек. Offer не является track until
admin связывает его с existing track or future accepted catalog item.

## Requirements

### Requirement: Public offer submission

Система SHALL allow public clients to submit YouTube URLs as offers without an
admin token.

#### Scenario: Offer is submitted

- **WHEN** client posts `youtube_url` to `/api/offers/add`
- **THEN** repository creates an offer with status `new`
- **AND** response returns the new `offer_id`

### Requirement: Offer listing and lookup

Система SHALL expose offer listing and single offer lookup through the API.

#### Scenario: Offers are listed

- **WHEN** client requests `/api/offers`
- **THEN** API returns offers ordered by newest first
- **AND** optional status filter limits the returned status

#### Scenario: Missing offer is requested

- **WHEN** client requests an unknown offer id
- **THEN** API returns `404`

### Requirement: Admin offer processing

Система MUST require admin bearer auth for accepting or cancelling offers.

#### Scenario: Offer is accepted

- **WHEN** admin accepts a `new` offer with a track id
- **THEN** repository marks it `accepted`, stores `accepted_track_id`, and sets `processed_at`

#### Scenario: Offer is cancelled

- **WHEN** admin cancels a `new` offer
- **THEN** repository marks it `cancelled` and sets `processed_at`

### Requirement: Offer metadata annotation

Система SHALL allow offer metadata to be filled incrementally without replacing
already stored fields with null values.

#### Scenario: Metadata is partially known

- **WHEN** code annotates only title or youtube id
- **THEN** repository updates provided fields
- **AND** omitted metadata fields remain unchanged
