# Learnings

Topical reference. Each entry links to a knowledge file.
**Rule**: on tool-call failure or user correction, update relevant knowledge file immediately — don't defer.

## Knowledge Files

- [Git operations & conventions](knowledge/git.md) — branch membership, git show RTK trap, branch/commit naming
- [Worktrees, node_modules, lockfiles](knowledge/worktrees.md) — pnpm/npm/husky/symlink patterns per repo
- [PR & GitHub workflow](knowledge/pr-workflow.md) — gh commands, state checks, template conventions
- [Playwright patterns](knowledge/playwright.md) — multi-scenario reload, dev proxy, login flow, selectors
- [webui2 browser validation](knowledge/webui2-testing.md) — hybrid stack, RBAC/flag gate, route discrimination
- [mf-cfw: CI & Playwright](knowledge/mf-cfw.md) — SonarQube gate, coverage, Cypress/Playwright build
- [webui PHP & testing](knowledge/webui-php.md) — PHPUnit, steering exceptions, no-vendor-symlink traps
- [Local devbox docker stack](knowledge/devbox.md) — docker compose, angular-ui, dev-lazy build, worktree swap
- [API contracts & Jira](knowledge/api-contracts.md) — v2 hygiene, Jira search, field IDs, ADF, Atlassian curl
- [Frontend patterns](knowledge/frontend.md) — Angular interceptors, React/RQ/TanStack, Vitest, flags, npm/pnpm
- [Infra: Nginx, K8s, GH Actions](knowledge/infra.md) — ngweb_mf fallback, auth_request masquerade, local action refs
- [Process & tooling](knowledge/process.md) — debugging discipline, caveman comments, RTK proxy, opsx commands
- [vanguard (netskope-qe/vanguard E2E)](knowledge/vanguard.md) — uv sync extras, KB batch-mode branch strategy
- [webui validation advice (boot-bugfix/boot-feature)](knowledge/webui-advise.md) — split evidence by side: Playwright screenshots for Angular/React, curl req/resp + CSRF mark-out/revert for PHP

## Multi-file `git diff HEAD -- $VAR` returns 0 lines in zsh (2026-09-05)
- `git diff HEAD -- $FILES` where `$FILES="a b c"` (unquoted var holding space-separated
  paths) silently diffed nothing, and `for f in $FILES; do ...; done` iterated ONCE with
  the whole string as one item — because this environment's shell is **zsh**, and zsh does
  NOT word-split unquoted variable expansions by default (unlike bash). Git received one
  literal pathspec `"a b c"` (with embedded spaces), matched nothing, diffed nothing.
  `rtk proxy git diff ...` piped straight to `wc -l` appeared to "fix" it once, but that was
  a red herring (rtk output vanished when redirected into a `{ } > file` group in the same
  session — inconsistent, don't trust it as the fix).
- Real fix: never build a multi-path git pathspec through a bare shell variable in zsh. Use
  either (a) an explicit literal path per `git diff HEAD -- "path"` invocation (one per
  line/call), or (b) a zsh array (`FILES=(a b c); git diff HEAD -- $FILES[@]`) or
  `${=FILES}` (forces word-split) if a variable is required. Applies to vanguard's
  local-pr-review.md phase and any other multi-file git command built from a joined string.
