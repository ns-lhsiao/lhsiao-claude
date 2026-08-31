## 1. Scaffold boot-playwright skill

- [x] 1.1 Create `~/.claude/skills/boot-playwright/` with `SKILL.md` frontmatter
      (name, description, `user-invocable: true`, allowed-tools) and a
      `recipes/` subdirectory
- [x] 1.2 Write `SKILL.md` shared-knowledge sections: `playwright-cli` session
      lifecycle (open/reuse by `-s=<name>`), credential `.env` convention,
      cleanup — carry forward the argument contract (`/boot-playwright <recipe>
      <slug>`) and the "list valid recipes and stop" behavior for a missing/bad
      recipe name

## 2. Write shared login/nav/validation knowledge into SKILL.md

- [x] 2.1 Login flow section: locallogin form, wait for hash to leave `/login`,
      dismiss welcome wizard — ported from `mf-client-playwright` /
      `webui-devbox-playwright`, generalized (no skill-specific paths)
- [x] 2.2 SPA hash-navigation section: hash assignment via `playwright-cli eval`,
      never `goto` post-login
- [x] 2.3 Headless-Chrome UA spoof section (`channel: chrome`,
      `ignoreHTTPSErrors`, spoofed UA string) with an explicit note that
      `webui2-angular-shell-devbox` is the one recipe that must NOT use it
      (headed only)
- [x] 2.4 Validation-plan format + per-step PASS/FAIL/screenshot report template
      + "never close the session" convention, using `playwright-cli screenshot`

## 3. Write recipes/webui-angular-devbox.md (base)

- [x] 3.1 Port the SLOT/port-formula section from `init-dev-env` (devbox `web`
      TLS `8443+SLOT`, `angular-ui` `4200+SLOT`) and the per-slug compose
      override steps
- [x] 3.2 Port worktree one-time setup from `webui-devbox-playwright`: `vendor/`
      real-copy rule (never symlink — CodeIgniter double-include), `node_modules`
      symlink-if-lockfiles-match rule, dev-lazy Angular build
- [x] 3.3 Port `rbac-css` stash application + cert-rotation-notice cookie bypass
      + view/subview two-hash-navigation quirk + list-data 60s polling patience
- [x] 3.4 Port teardown steps (remove per-slug containers only, never `down` the
      shared project; discard worktree stash/edits)

## 4. Write recipes/webui-angular-devbox-mf-client.md (layered)

- [x] 4.1 Opening section: point to `webui-angular-devbox.md` as a prerequisite
- [x] 4.2 Port mf-client dev-server startup (`PORT=$MFCLIENT_PORT`,
      `FAST_REFRESH=false WDS_HOT=false` workaround) and dev-proxy startup
      (edit worktree `src/main.ts` port + target URL) from `init-dev-env`
      steps 6-7
- [x] 4.3 Port MF-load-readiness wait selector and the mf-client-specific
      teardown (kill background dev-server/proxy processes, discard proxy
      `src/main.ts` edits) from `mf-client-playwright`

## 5. Write recipes/webui-angular-devbox-mf-cfw.md (layered)

- [x] 5.1 Opening section: point to `webui-angular-devbox.md` as a prerequisite
      (only for Playwright/QA-tenant mode; note Cypress mode needs no devbox)
- [x] 5.2 Port mf-cfw dev-server startup (yarn/craco, port 8014) and the mode
      comparison table (Cypress RBAC-mock vs. Playwright) from `mf-cfw-playwright`
- [x] 5.3 Port Cypress RBAC-intercept pattern and Playwright standalone /
      QA-tenant-via-proxy base-URL options, dropping the ENG-1118301 DNS
      Security ticket-specific section entirely (not migrated)

## 6. Write recipes/webui2-angular-shell-devbox.md (new)

- [x] 6.1 Port the hybrid-mode setup from `/wb:setup:angular-shell`: repo
      locate, Angular dist check, `.env.local` write (angularHybridPlugin vars),
      ms-webui + Vite dev-server startup, headed-only login note
- [x] 6.2 Backfill from `/wb:setup:webui2-shell`: MariaDB/Colima liveness check
      (Step 0), `/pinger` added to `PUBLIC_LOCAL_API_PATHS`, curl-based
      health-check retry loops with kill-on-failure for ms-webui and Vite,
      `dev-backend.sh`-missing fallback (`go run ./cmd/ms-webui/`),
      dependency-install skip-if-present step
- [x] 6.3 Port troubleshooting table (`balkan_pages` sessionStorage cache,
      `signed_off_pages.json` staleness, `ANGULAR_DIST_DIR not found`, RBAC/pinger
      timeout, nav-highlight mismatch) plus the headless-UA-rejection symptom
      ("Safari 0 is not supported") as its own troubleshooting entry

## 7. Update boot-bugfix and boot-feature

- [x] 7.1 Rewrite `boot-bugfix` Phase 5 to invoke
      `/boot-playwright <recipe> <slug>` (recipe chosen from the touched UI
      area) in place of the inline `/init-dev-env` + `playwright-cli` steps
- [x] 7.2 Rewrite `boot-feature` Step 3.5 the same way, keeping the
      "skip if no UI surface" gate

## 8. Deprecate legacy skills

- [x] 8.1 Replace `webui-devbox-playwright/SKILL.md`, `init-dev-env/SKILL.md`,
      `mf-cfw-playwright/SKILL.md`, and `mf-client-playwright/SKILL.md` frontmatter
      `description` with a leading "Deprecated — use `boot-playwright`" notice
- [x] 8.2 Replace each of the four bodies with a one-line pointer to
      `boot-playwright` (and its relevant recipe file); leave directories and
      non-`SKILL.md` files (e.g. `mf-client-playwright/.env`) in place

## 9. Verify

- [x] 9.1 Read all five new/modified skill files back end-to-end for internal
      consistency (recipe cross-references resolve, no leftover references to
      deleted content)
- [x] 9.2 Confirm no secrets or tenant-specific credentials were introduced into
      any recipe file (per global CLAUDE.md sensitive-data rule)
