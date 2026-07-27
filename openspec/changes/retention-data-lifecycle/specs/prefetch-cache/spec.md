## MODIFIED Requirements

### Requirement: Cache limits

The prefetch cache maintenance MUST enforce cold cache byte quota and hot cache item count without deleting audio
referenced by active catalog tracks, queued playback, or the currently playing track.

#### Scenario: Cold cache exceeds quota

- **WHEN** cold cache total size is greater than configured quota
- **THEN** oldest unprotected files are removed until usage is within quota
- **AND** protected files remain even when the quota cannot be satisfied

#### Scenario: Hot cache overflows

- **WHEN** hot cache has more files than `hot_max_items`
- **THEN** oldest unprotected files are removed
- **AND** protected files remain available to playback
