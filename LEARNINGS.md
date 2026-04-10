# Learnings

## mf-client Is a Separate Git Repo Inside netskope-ng-base

- `netskope-ng-base/frontends/mf-client` has its own `.git` with remote
  `git@github.com:netSkope/mf-client.git`. It is NOT a subdirectory of
  `netskope-ng-base` for git purposes. Always `cd` into the mf-client
  directory and check `git remote -v` before running git/gh commands.
  Release branches (e.g., `release/202605.2`) exist on the mf-client
  remote, not on netskope-ng-base.

## gh pr edit Requires read:project Scope

- `gh pr edit <number> --body "..."` fails with "authentication token is
  missing required scopes [read:project]". Use the REST API instead:
  `gh api repos/OWNER/REPO/pulls/N -X PATCH -f body="..."`. The `-X PATCH`
  is required — the default method won't work.

## mcp.json Contains Secrets — Never Track in Git

- `~/.claude/mcp.json` stores API tokens (e.g., `ATLASSIAN_API_TOKEN`) in
  plaintext under `mcpServers.*.env`. This file must NEVER be committed.
  The `.gitignore` in the config repo explicitly excludes it.

## Atlassian MCP Server May Not Expose Direct Tools

- Even when `~/.claude/mcp.json` configures an Atlassian MCP server, the
  tools may not be available in the session. Fallback: use `curl` with the
  Jira REST API v3 directly:
  `curl -s -u "USER:TOKEN" "https://SITE/rest/api/3/issue/KEY?fields=summary,description,status"`
  where credentials are read from `mcp.json` via
  `jq -r '.mcpServers.atlassian.env.ATLASSIAN_API_TOKEN' ~/.claude/mcp.json`.

