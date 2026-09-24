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

## Seed tenant step needs `--api-token` for SCIM seeders (2026-09-24)
- `python -m vanguard.seeding seed` builds its token-auth `api_client` from `--api-token`
  (settings alias `API_TOKEN`). Both `nightly.yml` and `test.yml` Seed tenant steps only passed
  `--username/--password`, so SCIM-backed seeders (`users_groups` group/VDI top-up) hit 401 on
  every call while pytest in the same job had the token. Symptom: seed report says SUCCESS with
  `users_groups: 0 created`; TC-CLIENT-243 red. Fix: add
  `${{ secrets.API_TOKEN && format('--api-token "{0}"', secrets.API_TOKEN) || '' }}` to the
  seed command (PR #1423, 6a65e4fb). The seed CLI's own report is not a health signal — read the
  per-seeder WARNING lines or the pre-flight test.
- `test.yml` has an optional `seed_manifest` dispatch input since 573ec5fc — use it to reproduce a
  nightly leg's seeded state instead of waiting for the schedule.
- client2 answers `500 {"error":{"message":"tenant configuration incomplete"}}` to any
  `privateAccess.preLogon` write, so unlocking `nplan669_prelogon_config_enabled` turns 6 pre-logon
  skips into UI-assertion failures (modal stays open, cert field absent). Needs a backend
  capability gate, not a flag gate.

## GitHub Actions log scraping from macOS (2026-09-24)
- `gh run view <id> --log` lines are `job\tstep\ttimestamp message`; split with
  `awk -F'\t' '$1=="test" && $2=="Seed tenant"{print $3}'`. macOS grep has no `-P`; the `grep`
  hook may route to ugrep which rejects long alternations ("exceeds complexity limits") — keep
  patterns short or use awk.
- Live job logs (`gh api .../jobs/<id>/logs`) return `BlobNotFound` until the job completes; the
  step conclusion via `gh run view --json jobs` is available immediately.
- `$TMPDIR` differs between sandboxed (`/tmp/claude-501/...`) and `dangerouslyDisableSandbox`
  (`/var/folders/.../T/`) Bash calls — files written by one are not at `$TMPDIR` in the other.
  Use the absolute `/var/folders/...` path when reading back.

## Client Configuration suite on a shared tenant: orphan rows break everything (2026-09-24)
- The Client Configuration grid pages at 10 rows. Any test that opens its own row via
  `client-configuration-name-<id>` looks on page 1 only, so >9 leftover `auto_test_*` rows turn
  the whole suite into 30 s `Locator.click` timeouts (run 35960565467: 50/1/34/16). Diagnose from
  the footer text in count_integrity failures (`1 - 10 of 24`) and `direct_hash_url` listing old
  `auto_test_<ms>_<uuid>_NNN` names.
- Leak source: a fixture that creates N rows in a loop and raises before `yield` never reaches its
  teardown. Wrap the loop in try/except, delete what was created, re-raise
  (`many_seeded_client_configs`).
- Seed-time cleanup (`client_configuration_cleanup`) runs under the nightly tenant lock, so every
  `auto_test_*` row present is an orphan: manifest `max_age_hours: 0`. A 1 h or 24 h cutoff let
  44-min-old orphans through.
- client2's clientconfiguration API returns 503 on TC-226's 31-row create burst, 3 of 3 seeded runs
  (04:52, 06:41, 08:28 UTC). Service-side issue; the burst also stalls the tenant for minutes.
- Seeded baseline after PR #1423 (102be6a7): 84/1/14/2 in 1 h 42 on one xdist worker. Residuals:
  5 pre-logon (`500 tenant configuration incomplete`), 5 version drift (footer counts Default row;
  "Allow disabling of Private Access" not rendered with flag on), 1 fail-close routing, 2 column-
  settings PUT timeouts (pre-existing), 1 TC-226 503, 2 load flakes.
- Local venv without `--extra visual` fails `tests/unit/visual/test_judge_plumbing.py` (anthropic)
  and mypy on `visual/judge.py`; `tests/unit/nightly_dashboard` needs jinja2 after #1460. Both
  unrelated to branch work; CI installs `--all-extras`.
