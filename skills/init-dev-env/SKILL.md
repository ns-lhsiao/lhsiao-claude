---
name: init-dev-env
description: >-
  Deprecated — use boot-playwright. Per-worktree devbox/mf-client/proxy stack
  bootstrap now lives in the webui-angular-devbox and
  webui-angular-devbox-mf-client recipes under boot-playwright.
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Grep
---

# Init Dev Env (deprecated)

Superseded by `/boot-playwright webui-angular-devbox-mf-client <slug>` (which
layers on the `webui-angular-devbox` base recipe for the devbox-ui stack). See
`~/.claude/skills/boot-playwright/SKILL.md` and
`~/.claude/skills/boot-playwright/recipes/webui-angular-devbox.md` +
`~/.claude/skills/boot-playwright/recipes/webui-angular-devbox-mf-client.md`.

The slot registry this skill created, `/Users/lhsiao/ns/git/devbox-ui/.devenv-slots.json`,
is still the registry `boot-playwright`'s base recipe reads/writes — left in place.
