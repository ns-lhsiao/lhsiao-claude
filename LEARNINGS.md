# Learnings

Topical reference. Each entry links to a knowledge file.
**Rule**: on tool-call failure or user correction, update relevant knowledge file immediately — don't defer.
Never add inline entries below the index — put content in the knowledge file and index it here.

## Knowledge Files

- [Git operations & conventions](knowledge/git.md) — branch membership, git show RTK trap, zsh word-split + `$VAR:path` modifier traps, mf-cfw commitlint (`ENG-NNN: subject`), webui2 narrow fetch refspec → `gh pr create --head` + config-set tracking
- [Worktrees, node_modules, lockfiles](knowledge/worktrees.md) — pnpm/npm/husky/symlink patterns, isolation guard (Edit/Write outside worktree, computed strings/heredocs), sandbox vs EnterWorktree, `.claude/worktrees/` scratch trap, dangling symlinks, script-file chore patterns, webui neo npm→pnpm migration (corepack shim broken, artifactory/VPN, empty-node_modules exit-0 trap)
- [PR & GitHub workflow](knowledge/pr-workflow.md) — gh commands, state checks, template conventions, ruleset-blocked branch delete, `gh pr edit` read:project + REST PATCH bypass, sq-parse.py args, npm mirror lag, reviewer `ns-` logins
- [Playwright patterns](knowledge/playwright.md) — multi-scenario reload, dev proxy, login flow, selectors, SPA session drop on goto/reload, long session names truncate daemon socket
- [webui2 browser validation](knowledge/webui2-testing.md) — hybrid stack, RBAC/flag gate, route discrimination, `/pinger` POST trap, login paths (`/locallogin`), dual-mount rc flags, `VITE_FLAG_OVERRIDES`/`VITE_FORCE_FLAGS`, MSW fixture edits, Fail-Close interstitial, IPv6 `ipv4first`, DTC watchdog noise, pure-MSW `pnpm dev` needs `ENABLE_WEBUI_PROXY=false` + `/ns/#/` hash routes
- [mf-cfw: CI & Playwright](knowledge/mf-cfw.md) — SonarQube gate, coverage, Cypress/Playwright build, `__preview__/` harness + MSW, dev-proxy real-tenant validation, jest traps (resetMocks, jsdom-compat env, `yarn test` only), OpenAPI optional-field guard
- [mf-client (netskope-ng-base/frontends/mf-client)](knowledge/mf-client.md) — `yarn test` (craco) not `npx jest`, jsdom29 docblock for MutationObserver, submodule-bump flow
- [webui PHP & testing](knowledge/webui-php.md) — PHPUnit, steering exceptions, no-vendor-symlink traps
- [Local devbox docker stack](knowledge/devbox.md) — docker compose, angular-ui, dev-lazy build, worktree swap, restart recovery + RTP save quirks, OrbStack docker context, VPN-toggle kills docker+browser, web container remount steal, skopeit network-events 4-gate unlock, admin password reset, worktree-add `.claude/` sandbox trap, pure-curl login + clientConfiguration save validation traps
- [API contracts & Jira](knowledge/api-contracts.md) — v2 hygiene, Jira search, field IDs, ADF, Atlassian curl, Confluence v2 footer-comments (MARKDOWN), Jira v3-404 → retry v2
- [Frontend patterns](knowledge/frontend.md) — Angular interceptors, React/RQ/TanStack, Vitest, flags, npm/pnpm, abs-pos margin no-op, `h-full`/`truncate` CSS traps, jest mock traps (globalThis holder, rejects re-invoke), MFE wrapper READY event, dropdown/Popover unmount behavior, MSW `server.use` LIFO, RQ5 notify batching vs `act()`, webui Network Events flag-forked dual impl (skopeit vs legacy WhitelistSidePanel)
- [Infra: Nginx, K8s, GH Actions](knowledge/infra.md) — ngweb_mf fallback, auth_request masquerade, local action refs, pns_deploy zero-pad verify
- [Process & tooling](knowledge/process.md) — debugging discipline, caveman comments, RTK proxy (grep/`git show` mangling, worktree-guard false positives), sandbox behaviors (TLS, yarn/push, monitors), openspec archive/validate gotchas, background Bash wrapper, Figma MCP rate limits, stash-baseline proofs, i18n value check, private Google Sheets via SSO profile (export tsv, not gviz), sandboxed vs unsandboxed `$TMPDIR` mismatch, mf-cfw local ai-review recipe + snapshot overlay trap, zsh `echo ===` equals-expansion trap, SonarQube webui project keys (`webui-php`/`webui-client-neo`) + coverage-gap `?%` trap, curl --trace-ascii redaction leak
- [vanguard (netskope-qe/vanguard E2E)](knowledge/vanguard.md) — uv sync extras, KB batch-mode branch strategy
- [webui validation advice (boot-bugfix/boot-feature)](knowledge/webui-advise.md) — split evidence by side: Playwright screenshots for Angular/React, curl req/resp + CSRF mark-out/revert for PHP
- [CM tickets & flag rollouts](knowledge/cm-rollouts.md) — MP deployment windows (UTC table), 1-CM-per-window rule, soak/health-validation requirements, SOP bulk scripts (-s/-t hosts), ng_devices_enabled 4-region split example, BOM3 DC option IDs
- [Global FF rollout review](knowledge/feature-flag-review.md) — #global-feature-flag-rollout-review process (SRE+Support sign-off, 3-day SLA), health-validation-not-just-success, soak ≥1 business day, capture pre-state in CM comments, IMF-1271/EIMF-154 cautionary tales
