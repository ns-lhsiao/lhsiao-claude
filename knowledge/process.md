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

## Background Bash Tool: long-running servers need nohup + disown

- **`cmd > log 2>&1 & echo pid $!` with the Bash tool's `run_in_background: true` still gets the child killed when the wrapping shell exits.** A trailing `&` alone backgrounds the job only within that one shell invocation; when the tool's own wrapper process exits after the command returns, unadopted children get SIGHUP'd. Symptom: task-notification reports the backgrounded command "completed (exit code 0)" almost immediately, with the dev-server log showing only the startup echo and no server output — the process was never actually alive to serve requests. Fix: `nohup env VAR=val cmd > log 2>&1 & disown; echo "started pid $!"` — `nohup` ignores SIGHUP, `disown` removes it from the shell's job table so it survives the wrapper exiting. Confirmed 2026-09-10 (ENG-1268247, mf-client dev server + development-proxy via `boot-playwright`).

## Read Tool Strips/Converts HTML Markup

- **The `Read` tool does not show raw bytes for `.html` files — it renders a converted, tag-stripped text view.** A `.html` file containing a real `<!DOCTYPE html>` + `<style>` block (dark-theme CSS vars, tables, etc.) came back from `Read` looking like plain Markdown (`# Heading`, bare bullet lists, no tags at all). This is misleading when the goal is to reuse an existing HTML file's markup verbatim as a template — `Read`'s view will NOT show you the actual tags to copy. Fix: use `Bash` (`cat`/`sed -n`) to view the real source when you need exact bytes to reuse; only trust `Read` for prose/content review, not markup extraction. Hit 2026-09-13 while trying to copy CLAUDE.md's referenced "stylish" HTML report template verbatim — `Read` made it look like the reference file was plain Markdown, contradicting CLAUDE.md's description of it as a dark-GitHub-themed HTML doc with CSS vars; a direct `sed`/`cat` would have shown the truth immediately instead of building a new template from the written spec alone.

## RTK Proxy

- **RTK hook swallows grep output in some contexts.** Bare `grep` via the shell hook shows `"X matches in 0 files: [+N more]"` with no actual content. Fix: prefix with `rtk proxy` — e.g. `rtk proxy grep -n "pattern" file.php`. Same applies to other commands whose output RTK filters but shouldn't.
- **RTK's `find` wrapper rejects compound predicates.** `find . -iname "X" -o -iname "Y"` errors with `rtk find does not support compound predicates or actions (e.g. -not, -exec). Use find directly.` Fix: either run two separate single-predicate `find` calls, or fall back to plain `grep`/`find` without the RTK hook for anything needing `-o`/`-not`/`-exec`.
- **RTK's `grep` is ripgrep underneath — BRE-style `\|` alternation with literal parens can throw `regex parse error: unclosed group`.** `grep -n 'foo(\|bar('` fails; ripgrep doesn't parse the escaped-parenthesis-before-`\|` the way GNU grep's BRE does. Fix: use `grep -nE 'foo\(|bar\('` (extended regex, escape the literal paren, unescaped `|`).

## Collecting Secrets From the User

- **`AskUserQuestion` cannot collect a free-text secret value.** Selecting an option only returns that option's LABEL text back to the assistant — even an option literally titled "Give me the password" resolves to that label string, never a value the user typed. If you need a secret (password, token), ask a plain follow-up question in normal chat instead of routing it through `AskUserQuestion` — the tool is for choosing among fixed alternatives, not free-text collection. Confirmed 2026-08-27/28: two consecutive attempts to collect a devbox password via `AskUserQuestion` options both returned only the option label with no secret attached.
- **Warn the user explicitly not to prefix a secret with `!` when typing it as a reply.** The `!` prefix runs the line as a shell command in this harness; a user pasting a bare password in response to "type the password" can trigger `! Change#123` unintentionally if muscle-memory from other prompts kicks in, surfacing as `command not found` in a `<bash-input>/<bash-stdout>` block instead of reaching you as chat text. When asking for a secret, say "type it as plain text, no `!` prefix."

## Resuming Background Agents

- **`Agent` tool never resumes — it always starts fresh (unless `subagent_type: "fork"`).** Passing a prior agent's ID/name as `to:` to `Agent` is silently accepted but spawns a NEW agent with zero context; it just bounces back asking "what ticket/context?" To continue a previously spawned agent (e.g. an `issue-root-causing` agent waiting on a user decision before it writes to Jira), use `SendMessage({to: "<agentId or name>", message: "..."})` instead. Confirmed 2026-08-28: called `Agent({to: "abb2c33..."})` expecting a resume, got a fresh agent with no memory of the RCA draft it was supposed to push.

## netSkope/service (provisioner-pycore): no local test env

- **`components/provisioner-pycore` cannot run its own test suite locally in this sandbox.** `tox.ini` requires a conda env (`tox-conda`, `app-env-py312.yaml`) with internal-only packages (`provisioner_common`, etc.) that aren't installable here (no `conda` binary, no PyPI mirror for those packages) and aren't vendored in the repo (`find ... -iname provisioner_common` under the component returns nothing — it's an external dependency, not a local module). This isn't sandbox-specific bad luck — PR #106895 (ENG-1074579) itself documented the same constraint in its own test plan ("local env doesn't have pytest; new tests compile-clean"). Fix: don't attempt to bootstrap the env; instead `python3 -m py_compile <file>` for a syntax check, manually trace logic against the actual call sites, and defer real execution to CI/drone — matching established precedent for this component. Confirmed 2026-09-13.
- **Cross-file constant-sharing direction matters for circular imports — check which file already imports which before "de-duplicating" a literal.** `route.py` already does `from .other_config import ... CRONJOB_NAME ...`; the natural instinct to put a NEW shared constant in `route.py` (since it "owns" the Flask route registration) and import it INTO `other_config.py` would create a circular import (`other_config.py` → `route.py` → `other_config.py`). Caught this before implementing, not after a failure — but it's a cheap, easy-to-miss trap: always check `grep -n "^from \.\|^from <pkg>" <file>` on both files first and put the new constant in whichever file is already the "imported-from" side of that pair.

## OpenSpec (opsx) Slash Commands

- **`/opsx:propose` doesn't exist** — CLAUDE.md's Planning-with-OpenSpec section names `/opsx:propose`, `/opsx:apply`, `/opsx:archive`, but the actual installed skill set is `opsx:new` (start a change + generate artifacts), `opsx:continue`, `opsx:ff` (new + all artifacts in one go), `opsx:apply`, `opsx:archive`, `opsx:verify`, `opsx:sync`, `opsx:explore`, `opsx:onboard`, `opsx:bulk-archive`. Calling `Skill({skill: "opsx:propose"})` throws `Unknown skill`. Use `opsx:new` for the propose step (or `opsx:ff` for propose+artifacts combined) until CLAUDE.md is corrected.
- **webui repo names its OpenSpec skills without the `opsx:` prefix.** In webui, the ff/apply/archive/explore skills are listed unscoped as `openspec-ff-change`, `openspec-apply-change`, `openspec-archive-change`, `openspec-explore` (not `opsx:ff` etc — that global-prefixed name throws `Unknown skill` there). Check the skill listing for the repo-specific name before calling.
- **Archiving a change whose delta spec is `## ADDED Requirements` for a brand-new capability (no existing `openspec/specs/<capability>/` to diff against) still needs an explicit sync step, or the capability ends up with NO main spec at all after archive.** The "assess delta spec sync state" logic naturally short-circuits when there's nothing to diff, making it easy to skip straight to `mv changes/<name> changes/archive/...` — but for an ADDED-only delta this silently drops the spec instead of landing it. Fix: after archiving, always check whether `openspec/specs/<capability>/spec.md` exists for every capability the change's proposal listed under "New Capabilities"; if not, `mkdir -p` it and write the (now-archived) delta content in as the new main spec (strip the `## ADDED Requirements` delta-op header, add a `## Purpose` line, keep the requirements/scenarios verbatim). Confirmed 2026-09-17 (ENG-1287334, webui `fix-rtp-negation-exclusion-strip`).
- **`openspec archive <name>` prompts interactively** ("Proceed with spec updates? (Y/n)") and fails with `User force closed the prompt` in a non-interactive session. Always pass `-y`/`--yes`: `openspec archive "<name>" -y`.

## Claude Desktop reads a per-workspace settings.json, NOT ~/.claude/settings.json

- **Hooks/permissions written to `~/.claude/settings.json` never fire in a Claude Desktop session**, even after `/hooks` reload or a restart. Desktop loads its runtime settings (hooks, permissions, theme) from `<workspace>/.claude-config/settings.json` (e.g. `/Users/lhsiao/ns/git/claudeDesktop/.claude-config/settings.json`) — a separate, much smaller file. `~/.claude/CLAUDE.md` and `~/.claude/LEARNINGS.md` DO still get loaded (confirmed present in system prompt), so it's not that `~/.claude` is ignored wholesale — just `settings.json` specifically resolves to the workspace copy in Desktop.
- Symptom: added a `PreToolUse` hook (matcher `Read`) to `~/.claude/settings.json`, committed/pushed it, confirmed via `jq` it was well-formed and present on disk — but a live `Read` call never triggered it. Added a sentinel-prefixed command (`date >> /tmp/....txt; <real cmd>`) and confirmed via the sentinel file that the hook process never ran at all.
- Fix: for hooks that must work inside Claude Desktop, also (or instead) edit `<workspace>/.claude-config/settings.json`. Note the Bash sandbox explicitly denies writes to that exact path (`denyWithinAllow`) even with `dangerouslyDisableSandbox` in some configurations — treat it as a protected file and confirm with the user before self-modifying it. Check which host is running (`ls <cwd>/.claude-config/settings.json`) before assuming `~/.claude/settings.json` is the effective config.

## zsh globbing in Bash tool commands

- `grep -r --include=*.ts .` fails with `(eval):1: no matches found: --include=*.ts`.
  zsh expands the bare `*` before grep sees it. **Always quote**: `--include="*.ts"`.
  Same trap as `--remote-allow-origins=*` for Chrome CDP.
- **RTK rewrites `grep` to `rg`: BRE alternation `\|` breaks when the pattern also contains `(`.** `grep -n "foo\|bar("` becomes an rg regex with an unclosed group → `regex parse error ... unclosed group`, zero matches. Use `rg -n "foo|bar\("` (PCRE-style alternation, escape parens) or `grep -E`. Plain `\|` alternation without parens still works. Hit 2026-09-03 (webui2 ENG-1252057).
- **Two dev servers from one Bash call both launched from the same checkout.** `cd <worktree> && (A &); (B &)` — the second launch inherits the `cd`; "Shell cwd was reset" only happens *between* tool calls. Wrap each launch in its own subshell with an explicit path: `(cd <worktree> && ... pnpm dev > /tmp/dev-after.log &)` then `(cd <primary> && ... pnpm dev > /tmp/dev-before.log &)`, and confirm per port with `lsof -p <vite pid> -a -d cwd -Fn` before screenshotting. Cost two restarts on 2026-09-03 (ENG-1252057).
- **`openspec status --change <name>` errors `Change '<name>' not found. No changes exist.` when cwd is inside `openspec/changes/<name>/`.** The CLI resolves `openspec/` from cwd upward but not from within a change dir. Run openspec commands from the repo root. 2026-09-03.

## Sandboxed Bash cannot write into a git worktree outside the session cwd (2026-09-22)
- Session cwd was `claudeDesktop/`; the vanguard worktree lives at a sibling path under
  `~/ns/git/`. Heredoc / python writes there failed with `Operation not permitted` because the
  Seatbelt write allowlist is only cwd + `$TMPDIR`. Fix: run the write command with
  `dangerouslyDisableSandbox: true` (the worktree IS the task target), or start the session from
  the worktree directory. Reads were unaffected.

## `cmd | tail -1 && next` masks the gate's exit code (2026-09-23)
- Chained `uv run mypy src/ | tail -1 && git commit ...`: mypy found 5 errors but the pipeline's
  status is `tail`'s (0), so the commit (and push) went through with type errors. Same trap for
  `pytest ... | tail -1`. Discovered when a later run showed "Found 5 errors" in the transcript
  after the push had already happened.
- Fix: never pipe a gate command whose exit code matters. Run it bare (`uv run mypy src/ &&
  ...`), or `set -o pipefail` first, or capture output to a file and `grep`/`tail` afterwards.
  In zsh/bash, `cmd | tail -1` always succeeds unless `pipefail` is set.
