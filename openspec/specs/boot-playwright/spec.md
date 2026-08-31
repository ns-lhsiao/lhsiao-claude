## ADDED Requirements

### Requirement: Explicit recipe + slug invocation
`/boot-playwright` SHALL require the caller to pass an explicit recipe identifier
and a slug; the skill SHALL NOT infer the recipe from changed files or any other
implicit signal.

#### Scenario: Caller names a valid recipe
- **WHEN** invoked as `/boot-playwright webui-angular-devbox-mf-client <slug>`
- **THEN** the skill loads `recipes/webui-angular-devbox-mf-client.md`, follows its
  "read the base recipe first" pointer to `recipes/webui-angular-devbox.md`, and
  executes the combined setup using `<slug>` for worktree/slot resolution

#### Scenario: Caller omits or misnames the recipe
- **WHEN** invoked with no recipe argument, or a recipe name that does not match one
  of the four files under `recipes/`
- **THEN** the skill SHALL list the four valid recipe names and stop, without
  guessing which one was intended

### Requirement: Shared session lifecycle via `playwright-cli`
All browser automation driven by `boot-playwright` (directly, or via `boot-bugfix`/
`boot-feature`) SHALL use named `playwright-cli` sessions (`-s=<name>`) for launch,
reuse, navigation, and screenshotting. No recipe or shared-knowledge section SHALL
hand-roll a raw `chromium.launchServer()` + ws-endpoint-file pattern.

#### Scenario: First invocation for a session name
- **WHEN** `playwright-cli -s=<name> open` runs and no session `<name>` exists yet
- **THEN** a new headless session is launched under that name (headed only for the
  webui2-angular-shell-devbox recipe, per its headless-UA-rejection exception)

#### Scenario: Repeat invocation reuses the session
- **WHEN** `playwright-cli -s=<name> open` runs and session `<name>` already exists
- **THEN** the existing session is reused, not relaunched, and no new browser
  process accumulates

### Requirement: Login and SPA navigation follow the shared pattern
Any recipe that authenticates against webui/webui2 SHALL use the shared login flow
(locallogin form, wait for hash to leave `/login`, dismiss the welcome wizard if
present) and SHALL navigate within the SPA via hash assignment, never via a full
page `goto`/reload after login.

#### Scenario: Login only runs when needed
- **WHEN** the current session's page URL is not `about:blank`, `/login`, or
  `/locallogin`
- **THEN** the login flow SHALL be skipped and the existing authenticated session
  reused

#### Scenario: Post-login navigation uses hash assignment
- **WHEN** navigating to a route after an authenticated session exists
- **THEN** navigation SHALL be performed via `window.location.hash = '#/...'`
  (e.g. via `playwright-cli eval`), not `page.goto()`, to avoid a full SPA reload

### Requirement: Validation plan and per-step reporting format
Every recipe-driven validation run SHALL produce a numbered validation plan
(what/selector/pass-condition per step) before executing, and SHALL report each
step's PASS/FAIL with an accompanying screenshot, without closing the browser
session on either outcome.

#### Scenario: All steps pass
- **WHEN** every planned step's pass condition is met
- **THEN** the run reports PASS for each step with its screenshot path, and leaves
  the `playwright-cli` session open for reuse

#### Scenario: A step fails
- **WHEN** a planned step's pass condition is not met
- **THEN** the run reports FAIL for that step with its screenshot path, continues
  reporting remaining steps, and leaves the session open (does not close the
  browser) so the failure state can be inspected

### Requirement: Recipe layering for MF-specific environments
`recipes/webui-angular-devbox-mf-client.md` and
`recipes/webui-angular-devbox-mf-cfw.md` SHALL each open by directing the reader to
`recipes/webui-angular-devbox.md` for base devbox-ui setup, and SHALL contain only
their own delta steps (dev server startup, proxy startup, MF-readiness wait) —
neither file SHALL repeat the base recipe's devbox-ui bring-up steps.

#### Scenario: mf-client recipe invoked standalone
- **WHEN** `recipes/webui-angular-devbox-mf-client.md` is read on its own, without
  first reading the base recipe
- **THEN** its opening section explicitly names `webui-angular-devbox.md` as a
  prerequisite to read and execute first

### Requirement: webui2-angular-shell-devbox recipe operational completeness
`recipes/webui2-angular-shell-devbox.md` SHALL include the operational checks
present in the `/wb:setup:webui2-shell` reference but absent from
`/wb:setup:angular-shell`: a MariaDB/Colima liveness check before starting
ms-webui, `/pinger` included in `PUBLIC_LOCAL_API_PATHS`, curl-based health-check
retry loops with kill-on-failure for both ms-webui and the Vite dev server, a
fallback direct `go run ./cmd/ms-webui/` path when `scripts/dev-backend.sh` is
absent, and a dependency-install skip-if-present step.

#### Scenario: MariaDB is not running when the recipe starts
- **WHEN** the recipe's Step 0 checks for a running MariaDB container and finds none
- **THEN** it starts Colima (if Docker is unavailable) and the MariaDB container,
  and waits for it to become ready before proceeding to ms-webui startup

#### Scenario: `scripts/dev-backend.sh` is missing
- **WHEN** the webui2 checkout does not have `scripts/dev-backend.sh`
- **THEN** the recipe falls back to starting ms-webui directly via
  `go run ./cmd/ms-webui/` with the same env vars, rather than failing outright

### Requirement: Headed-only exception is called out for webui2-angular-shell-devbox
`recipes/webui2-angular-shell-devbox.md` SHALL explicitly document that its target
QA tenant rejects the headless Chrome UA (unlike the other three recipes, which use
a headless-with-spoofed-UA default) and that browser automation against it MUST run
headed.

#### Scenario: Attempting headless against the hybrid stack
- **WHEN** a `playwright-cli` session for this recipe is opened headless
- **THEN** login is expected to stick on a spinner ("Safari 0 is not supported"),
  and the recipe's troubleshooting section identifies this exact symptom as the
  headless-UA rejection, directing the caller to reopen the session headed

### Requirement: Legacy skills point to boot-playwright instead of duplicating it
`webui-devbox-playwright`, `init-dev-env`, `mf-cfw-playwright`, and
`mf-client-playwright` SHALL each have their `SKILL.md` frontmatter `description`
and body replaced with a deprecation notice pointing to `boot-playwright`, and
SHALL NOT retain their prior standalone instructions. Their directories and any
non-`SKILL.md` files (e.g. `.env`) SHALL remain in place.

#### Scenario: A legacy skill is matched by name or trigger phrase
- **WHEN** `mf-client-playwright` (or any of the other three) would previously have
  matched a user's request
- **THEN** its frontmatter `description` leads with "Deprecated — use
  `boot-playwright`" so skill selection surfaces the replacement instead of stale
  instructions

### Requirement: boot-bugfix and boot-feature delegate Playwright validation
`boot-bugfix` Phase 5 and `boot-feature` Step 3.5 SHALL invoke
`/boot-playwright <recipe> <slug>` for browser validation, selecting `<recipe>` from
the UI area they just modified, instead of inlining dev-env bootstrap and Playwright
scripting instructions in their own `SKILL.md`.

#### Scenario: boot-bugfix validates a UI fix
- **WHEN** Phase 5 of `boot-bugfix` runs for a fix touching
  `netskope-ng-base/frontends/mf-client/`
- **THEN** it invokes `/boot-playwright webui-angular-devbox-mf-client <slug>` (using
  the same slug as its Phase 4 worktree) rather than separately invoking
  `/init-dev-env` and hand-writing `playwright-cli` steps
