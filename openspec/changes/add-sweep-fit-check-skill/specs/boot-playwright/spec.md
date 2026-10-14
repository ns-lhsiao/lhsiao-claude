## ADDED Requirements

### Requirement: Pre-recipe fit check for live-tenant targets
When the validation target is a real tenant rather than a local dev stack, `/boot-playwright` SHALL invoke `sweep-fit-check` before loading the recipe and SHALL ask the user before proceeding on any verdict other than `GO`.

#### Scenario: Live tenant target with a limited verdict
- **WHEN** `/boot-playwright` is invoked for a live tenant and the fit check returns `GO-WITH-LIMITS`
- **THEN** the skill SHALL present the blocked cases and side effects, use AskUserQuestion for the decision, and continue only on an explicit answer

#### Scenario: Local dev stack target
- **WHEN** the recipe targets a local dev stack
- **THEN** the fit check SHALL NOT be invoked
