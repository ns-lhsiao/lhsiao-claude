# Process & Tooling

## Caveman Comments in Source Files

- **Rule exists in global CLAUDE.md §Source Code Comments but kept drifting.** Symptom: wrote full-prose `#` comments in `.github/workflows/pr-sidecar.yaml` while caveman full was active. Fix: before writing ANY file with comments, explicitly apply caveman compression to comment prose — drop articles/filler/hedging, fragments OK. Code identifiers (function names, paths, flags) stay exact. Applies to all file types: TS `//`, YAML `#`, JSDoc bodies. Commit messages and PR bodies stay normal prose regardless.

## Process: Debugging & Design

- **When stuck after 2–3 fix attempts, delegate to a subagent**. Pass repro steps, every relevant file, each rejected hypothesis, and a length cap (≤400 words). Subagents read fresh without main-thread framing bias and find closure/memo/cache issues. Failure signature: three consecutive fix commits that don't change user-visible behavior — revert and delegate.
- **Design before fixing parity bugs**. If the fix touches >2 files OR crosses a serialization boundary OR depends on a flag whose v1 wiring isn't already in front of you, spawn a sub-agent to surface v1 truth first. Cite v1 file:line in the commit. Failure: shipping then needing immediate follow-up because round-trip parity broke.
- **Customer-reported `affectsVersion` is observation-time, not introduction-time.** Tickets default to "the version where QA noticed it"; that may be years after the bug shipped. Before calling something a regression, pickaxe the defective code path AND verify the bug is byte-identical on `develop`, the prior `Release<N-1>`, and `Release<N>`. If identical across all three, it's pre-existing debt re-surfaced — flag the delta on the ticket. Repro: ENG-1031514 (reported affectsVersion 132.0.0; bug actually shipped with LBS column default in 2019, byte-identical on develop / Release132 / Release137 / Release138).
- **Pickaxe by symbol AND literal — strings get renamed.** `git log -S '<literal>'` misses commits where the literal was edited. ENG-1031514: writer's `notes` parameter changed `'added from app_info'` → `'default ssl pinned app'` in ENG-614741 (2025-04-08); customer rows seeded earlier still carry the old literal, but pickaxe on the new literal hides the writer's full history. Trace by function name (`addNewFromAppInfoToTenantDb`) plus a stable structural marker (the SQL skeleton, table name) and corroborate.

## Bash Tool: Shell State & cwd Persistence

- **`source <file>` in one Bash call does NOT carry into a later, separate Bash call** — only cwd persists across calls, not shell variables. Symptom: `source .env` in call N, then `"$NS_TEST_USERNAME"` in call N+1 silently expanded to empty string (no error) inside a `playwright-cli fill` command. Fix: `source <file> && <command using $VAR>` combined in the SAME Bash invocation.
- **cwd persistence can silently fail for directories outside the session's normal working-tree roots** (e.g. an ad-hoc `git clone` under `/tmp`) — tool reported "Shell cwd was reset to <original dir>" after every command run there. Fix: always `cd <dir> && <command>` combined in one call when operating in a throwaway/external directory; don't rely on a prior `cd` sticking. Confirmed 2026-08-31 (ENG-1180724, pushing screenshots to a `/tmp` clone of `netSkope/pr-screenshots`).

## RTK Proxy

- **RTK hook swallows grep output in some contexts.** Bare `grep` via the shell hook shows `"X matches in 0 files: [+N more]"` with no actual content. Fix: prefix with `rtk proxy` — e.g. `rtk proxy grep -n "pattern" file.php`. Same applies to other commands whose output RTK filters but shouldn't.
- **RTK's `find` wrapper rejects compound predicates.** `find . -iname "X" -o -iname "Y"` errors with `rtk find does not support compound predicates or actions (e.g. -not, -exec). Use find directly.` Fix: either run two separate single-predicate `find` calls, or fall back to plain `grep`/`find` without the RTK hook for anything needing `-o`/`-not`/`-exec`.
- **RTK's `grep` is ripgrep underneath — BRE-style `\|` alternation with literal parens can throw `regex parse error: unclosed group`.** `grep -n 'foo(\|bar('` fails; ripgrep doesn't parse the escaped-parenthesis-before-`\|` the way GNU grep's BRE does. Fix: use `grep -nE 'foo\(|bar\('` (extended regex, escape the literal paren, unescaped `|`).

## Collecting Secrets From the User

- **`AskUserQuestion` cannot collect a free-text secret value.** Selecting an option only returns that option's LABEL text back to the assistant — even an option literally titled "Give me the password" resolves to that label string, never a value the user typed. If you need a secret (password, token), ask a plain follow-up question in normal chat instead of routing it through `AskUserQuestion` — the tool is for choosing among fixed alternatives, not free-text collection. Confirmed 2026-08-27/28: two consecutive attempts to collect a devbox password via `AskUserQuestion` options both returned only the option label with no secret attached.
- **Warn the user explicitly not to prefix a secret with `!` when typing it as a reply.** The `!` prefix runs the line as a shell command in this harness; a user pasting a bare password in response to "type the password" can trigger `! Change#123` unintentionally if muscle-memory from other prompts kicks in, surfacing as `command not found` in a `<bash-input>/<bash-stdout>` block instead of reaching you as chat text. When asking for a secret, say "type it as plain text, no `!` prefix."

## Resuming Background Agents

- **`Agent` tool never resumes — it always starts fresh (unless `subagent_type: "fork"`).** Passing a prior agent's ID/name as `to:` to `Agent` is silently accepted but spawns a NEW agent with zero context; it just bounces back asking "what ticket/context?" To continue a previously spawned agent (e.g. an `issue-root-causing` agent waiting on a user decision before it writes to Jira), use `SendMessage({to: "<agentId or name>", message: "..."})` instead. Confirmed 2026-08-28: called `Agent({to: "abb2c33..."})` expecting a resume, got a fresh agent with no memory of the RCA draft it was supposed to push.

## OpenSpec (opsx) Slash Commands

- **`/opsx:propose` doesn't exist** — CLAUDE.md's Planning-with-OpenSpec section names `/opsx:propose`, `/opsx:apply`, `/opsx:archive`, but the actual installed skill set is `opsx:new` (start a change + generate artifacts), `opsx:continue`, `opsx:ff` (new + all artifacts in one go), `opsx:apply`, `opsx:archive`, `opsx:verify`, `opsx:sync`, `opsx:explore`, `opsx:onboard`, `opsx:bulk-archive`. Calling `Skill({skill: "opsx:propose"})` throws `Unknown skill`. Use `opsx:new` for the propose step (or `opsx:ff` for propose+artifacts combined) until CLAUDE.md is corrected.
- **webui repo names its OpenSpec skills without the `opsx:` prefix.** In webui, the ff/apply/archive/explore skills are listed unscoped as `openspec-ff-change`, `openspec-apply-change`, `openspec-archive-change`, `openspec-explore` (not `opsx:ff` etc — that global-prefixed name throws `Unknown skill` there). Check the skill listing for the repo-specific name before calling.
- **`openspec archive <name>` prompts interactively** ("Proceed with spec updates? (Y/n)") and fails with `User force closed the prompt` in a non-interactive session. Always pass `-y`/`--yes`: `openspec archive "<name>" -y`.

## zsh globbing in Bash tool commands

- `grep -r --include=*.ts .` fails with `(eval):1: no matches found: --include=*.ts`.
  zsh expands the bare `*` before grep sees it. **Always quote**: `--include="*.ts"`.
  Same trap as `--remote-allow-origins=*` for Chrome CDP.
- **RTK rewrites `grep` to `rg`: BRE alternation `\|` breaks when the pattern also contains `(`.** `grep -n "foo\|bar("` becomes an rg regex with an unclosed group → `regex parse error ... unclosed group`, zero matches. Use `rg -n "foo|bar\("` (PCRE-style alternation, escape parens) or `grep -E`. Plain `\|` alternation without parens still works. Hit 2026-09-03 (webui2 ENG-1252057).
- **Two dev servers from one Bash call both launched from the same checkout.** `cd <worktree> && (A &); (B &)` — the second launch inherits the `cd`; "Shell cwd was reset" only happens *between* tool calls. Wrap each launch in its own subshell with an explicit path: `(cd <worktree> && ... pnpm dev > /tmp/dev-after.log &)` then `(cd <primary> && ... pnpm dev > /tmp/dev-before.log &)`, and confirm per port with `lsof -p <vite pid> -a -d cwd -Fn` before screenshotting. Cost two restarts on 2026-09-03 (ENG-1252057).
- **`openspec status --change <name>` errors `Change '<name>' not found. No changes exist.` when cwd is inside `openspec/changes/<name>/`.** The CLI resolves `openspec/` from cwd upward but not from within a change dir. Run openspec commands from the repo root. 2026-09-03.
