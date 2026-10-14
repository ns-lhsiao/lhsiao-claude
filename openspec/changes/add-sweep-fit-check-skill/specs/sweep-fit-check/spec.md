## ADDED Requirements

### Requirement: Read-only applicability analysis
`/sweep-fit-check` SHALL analyze a page or route on a real tenant using only read operations and SHALL NOT invoke any UI action or API call that creates, modifies, or deletes tenant data.

#### Scenario: Page contains a mutating action
- **WHEN** the target page exposes an action that mutates the tenant (for example "Run Analyze", which overwrites the last result)
- **THEN** the skill SHALL record it under `side_effects` with `reversible` and `effect`, and SHALL NOT trigger it

#### Scenario: Only GET requests are issued
- **WHEN** the skill probes endpoints declared for the page
- **THEN** every request SHALL use GET (or HEAD), and any endpoint requiring another method SHALL be marked `RUNNABLE` only by caller opt-in, not by the probe

### Requirement: Verdict contract
The skill SHALL write a JSON file containing `target.kind`, `renderer`, `access`, `side_effects`, `cases`, `untested_roles`, `verdict`, and `page_draft`, where `verdict` is one of `GO`, `GO-WITH-LIMITS`, or `STOP`, and each case is one of `RUNNABLE`, `BLOCKED:<reason>`, `N-A`, or `NEEDS-DESIGN`.

#### Scenario: Target renderer unreachable
- **WHEN** a required feature flag is off, the permission is absent, or the entry point does not mount
- **THEN** `verdict` SHALL be `STOP` and the affected cases SHALL be `BLOCKED` with the reason

#### Scenario: Some cases cannot be exercised
- **WHEN** any case is `BLOCKED`, `NEEDS-DESIGN`, or `untested_roles` is non-empty while the target is reachable
- **THEN** `verdict` SHALL be `GO-WITH-LIMITS`

### Requirement: Honest flag and role reporting
The skill SHALL report feature flag and control flag state separately, SHALL report a flag it cannot read as `unknown`, and SHALL list roles required by the page file that the current session cannot represent in `untested_roles`.

#### Scenario: Control flag not readable
- **WHEN** only the feature flag endpoint is available
- **THEN** the control flag SHALL be reported `unknown` and SHALL NOT be assumed enabled, with entry-point mounting recorded as separate evidence

#### Scenario: Single-role session
- **WHEN** the session is Tenant Admin and the page file lists a read-only or no-access role case
- **THEN** that role SHALL appear in `untested_roles` and the corresponding case SHALL NOT be reported `RUNNABLE`

### Requirement: Error-shaped 200 responses are errors
The skill SHALL classify an HTTP 200 response whose body has `success` equal to false, or lacks the expected `data` key, as an error and SHALL NOT count the endpoint as reachable.

#### Scenario: Envelope reports failure
- **WHEN** an endpoint returns 200 with `{"success": false, ...}`
- **THEN** the probe result for that endpoint SHALL be an error carrying the envelope message

### Requirement: Gate before test execution
Callers SHALL run the fit check on first use of a page and SHALL ask the user before proceeding when `verdict` is not `GO`; `--yes` SHALL permit proceeding only for `GO` and `GO-WITH-LIMITS`, never for `STOP`.

#### Scenario: Fresh page file
- **WHEN** a page file exists with `last_verified` within 60 days, or `--skip-fit` is passed
- **THEN** the fit check SHALL be skipped

#### Scenario: STOP with --yes
- **WHEN** the verdict is `STOP` and the caller passed `--yes`
- **THEN** the caller SHALL still ask the user and SHALL NOT proceed without an explicit answer

### Requirement: Draft page file
The skill SHALL emit a draft sweep page file in the existing `pages/_TEMPLATE.md` format to a staging path, and SHALL NOT overwrite an existing page file.

#### Scenario: Page file already exists
- **WHEN** `pages/<slug>.md` exists
- **THEN** the draft SHALL be written beside it as `<slug>.draft.md` and the differences SHALL be listed in the report

### Requirement: No credentials in outputs
The skill SHALL NOT write passwords, session cookies, or tokens into the JSON, the Markdown report, screenshots' captions, or the draft page file.

#### Scenario: Output scan
- **WHEN** the output directory is scanned for the tenant password or cookie values
- **THEN** no match SHALL be found
