# vanguard (netskope-qe/vanguard E2E repo)

## Environment setup

- **Plain `uv sync` does NOT install Playwright/pytest test-runner deps.** `pytest-playwright`
  and `pytest-base-url` (which registers `--base-url`/`--username`/`--password`) live under
  `[project.optional-dependencies] ui`, not the base `dependencies` list, even though
  `playwright` itself (the driver package) is in base deps. Symptom: `pytest --base-url=...`
  fails with `error: unrecognized arguments: --base-url=...` even though collection and
  `pytest --collect-only` work fine (those don't need the plugin). Fix: `uv sync --extra ui`.
  CLAUDE.md's "Environment Setup" section only says `uv sync` — doesn't mention the extra.
  Hit 2026-09-03/04 during KB batch automation (client/client-configuration, TC-CLIENT-161),
  in a repo clone another session had already `uv sync`'d without the extra.

## KB batch mode (`/wb:e2e:automate --kb-dir ...`) — branch strategy

- **verify-and-commit.md's per-TC lib/tests branch split (Step 11a "MANDATORY") is written for
  single-test mode, not batch mode.** Literally creating a new `e2e/<tc-id>-lib` +
  `e2e/<tc-id>-tests` branch pair per test case across a 100+ TC batch is impractical (100+ PRs).
  kb-batch-mode.md's own framing ("commit happens in Step 11 -- one commit per test") plus
  historical precedent (grouped commits like "feat(client): add Client SAML E2E tests (P0)" and
  PR #220 covering many TCs) point to: one branch for the whole batch/feature
  (`e2e/<feature>-tests`, cut from `main` once at batch start), one commit per TC on that same
  branch (library + test files together is fine at this granularity), single push + single PR
  at Step 13. Reconcile oversized-PR risk later via `/wb:split-pr` rather than juggling two
  diverging branches across dozens of sequential sub-agent invocations.

## `uv sync` fails with `invalid peer certificate: UnknownIssuer` (2026-09-22)

- `uv sync` in a fresh vanguard worktree died downloading `playwright` from
  `artifactory-rd.netskope.io` (redirects to an S3 presigned URL): `client error (Connect)
  ... invalid peer certificate: UnknownIssuer`. uv ships its own CA bundle (webpki) and does
  not see the Netskope root cert in the macOS keychain.
- Fix: `UV_NATIVE_TLS=1 uv sync --extra ui` (or `--native-tls`). Uses the system trust store;
  the download then succeeds. Also `uv run playwright install chromium` afterwards.
