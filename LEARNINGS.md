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
