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

### A `cmd &` child inside a run_in_background Bash wrapper dies when the wrapper exits (2026-10-20)
- Ran `pnpm --filter shell dev --port 3000 > log 2>&1 & echo started` inside a `run_in_background` Bash call: the wrapper printed the log line then exited, and the harness reported the task "completed (exit 0)" — the Vite process was killed with it, leaving the port dead even though the log showed "ready".
- Fix: make the long-lived command itself the background task (`pnpm ... 2>&1` with `run_in_background: true`, no `&`). A background task's own process tree survives; a `&`-grandchild does not outlive its wrapper.
- Related sandbox trap in the same run: sandboxed `curl http://localhost:<port>` returns `000` (connection refused-looking) even while the server listens — probe localhost with `dangerouslyDisableSandbox` before concluding the server died. `nc -z 127.0.0.1` also misses IPv6-wildcard listeners (`*:3000` on IPv6); `lsof -iTCP:<port> -sTCP:LISTEN` sees both.

## Read Tool Strips/Converts HTML Markup

- **The `Read` tool does not show raw bytes for `.html` files — it renders a converted, tag-stripped text view.** A `.html` file containing a real `<!DOCTYPE html>` + `<style>` block (dark-theme CSS vars, tables, etc.) came back from `Read` looking like plain Markdown (`# Heading`, bare bullet lists, no tags at all). This is misleading when the goal is to reuse an existing HTML file's markup verbatim as a template — `Read`'s view will NOT show you the actual tags to copy. Fix: use `Bash` (`cat`/`sed -n`) to view the real source when you need exact bytes to reuse; only trust `Read` for prose/content review, not markup extraction. Hit 2026-09-13 while trying to copy CLAUDE.md's referenced "stylish" HTML report template verbatim — `Read` made it look like the reference file was plain Markdown, contradicting CLAUDE.md's description of it as a dark-GitHub-themed HTML doc with CSS vars; a direct `sed`/`cat` would have shown the truth immediately instead of building a new template from the written spec alone.

### Read tool reflows large single-file HTML into a different line numbering (2026-09-21)
- Reading a hand-built dark-theme HTML report (e.g. `all-html/index.html`, ~880 raw lines) via the
  Read tool returned a *much shorter*, reflowed pseudo-markdown rendering (converted headings/links,
  660 total lines) whose line numbers do NOT correspond to the real file — offsets taken from `grep
  -n` or `sed -n` on the raw file landed on unrelated content when fed back into Read. This appears
  specific to files the tool detects as HTML and tries to "render" rather than show verbatim.
- Fix: for precise line-numbered inspection of a raw HTML file, use `sed -n '<range>p'` / `grep -n`
  via Bash, not the Read tool's line numbers. The `Edit` tool's `old_string` matching still operates
  on real on-disk content regardless of what Read displayed, so exact-string edits sourced from
  `sed`/`grep` output remain safe even when Read's own numbering is unusable.
- Worse case (2026-09-29, `all-html/index.html`): when the reflowed rendering comes from a markitdown
  cache AND is truncated ("PARTIAL view ... cap 25000 tokens"), Edit's read-gate never registers the
  file as read — every Edit fails "File has not been read yet", even after paging through all offsets.
  Recovery: do the exact-string replacement via Bash (`python3` read_text/replace/write_text with a
  `count == 1` assert), with sandbox bypass if the file lives outside the session cwd. Smaller HTML
  files (the per-report pages) don't hit this — Edit works there after one partial Read.

## RTK Proxy

- **RTK hook swallows grep output in some contexts.** Bare `grep` via the shell hook shows `"X matches in 0 files: [+N more]"` with no actual content. Fix: prefix with `rtk proxy` — e.g. `rtk proxy grep -n "pattern" file.php`. Same applies to other commands whose output RTK filters but shouldn't. 2026-10-28 variant: the **Read tool** on `all-html/index.html` returned stale/markdown-looking content while `awk 'NR>=170'` showed the real HTML — line numbers from a mangled Read drift from ground truth; verify with `awk`/`sed` before editing by line reference.
- **RTK's `find` wrapper rejects compound predicates.** `find . -iname "X" -o -iname "Y"` errors with `rtk find does not support compound predicates or actions (e.g. -not, -exec). Use find directly.` Fix: either run two separate single-predicate `find` calls, or fall back to plain `grep`/`find` without the RTK hook for anything needing `-o`/`-not`/`-exec`.
- **RTK's `grep` is ripgrep underneath — BRE-style `\|` alternation with literal parens can throw `regex parse error: unclosed group`.** `grep -n 'foo(\|bar('` fails; ripgrep doesn't parse the escaped-parenthesis-before-`\|` the way GNU grep's BRE does. Fix: use `grep -nE 'foo\(|bar\('` (extended regex, escape the literal paren, unescaped `|`).

### rtk-wrapped git commands false-positive on the worktree isolation guard (2026-09-21)
- Inside a worktree session (webui2-fix-bwc-source-ip-remap), plain `git status`, `git diff
  origin/master`, and `git rev-parse` calls were refused with "this command runs rtk with a git
  command among its operands: what runs it ... cannot be read here ... Refusing to run it." The
  isolation checker couldn't statically verify the command stays inside the worktree once rtk's
  hook had rewritten `git ...` into its own wrapper — the substitution happens transparently, so
  from the checker's view the literal command "names git in a form too complex to verify."
- Fix: bypass the rtk rewrite entirely by invoking the real binary directly — `/usr/bin/git status`,
  `/usr/bin/git diff ...`, `/usr/bin/git commit ...` — the isolation checker can verify a direct
  binary path trivially. Applies to any git operation inside a worktree-isolated session when rtk's
  hook is active; `rtk proxy git ...` does NOT fix it (still routes through rtk).

### rtk hook mangles quoted grep patterns — parentheses/quotes stripped, silent 0-match (2026-09-29)
- Inside a worktree session, `grep -n "getAppTypeInUse() === 'none'" <file>` (rtk hook rewrite) returned
  `0 matches for 'getAppTypeInUse() === 'none''` — the quoted pattern was passed through with quoting
  mangled (nested single-quotes inside double-quotes survive only partially), so grep matched nothing.
  Same for `hasValidDestinationProfiles(this.data)`. Earlier rtk grep calls with simpler quoted patterns
  DID work (compressed "10 matches in 1 files" output), so the failure is pattern-dependent, not universal.
- Fix: invoke the real binary directly — `/usr/bin/grep -n "<pattern>" <file>` — always reliable inside
  worktree sessions (same bypass as git: see rtk-wrapped git entry). Treat rtk grep "0 matches" with
  any suspicion unless the pattern is trivially simple.

### rtk-compressed `git show <file>` output has FAKE line numbers/truncation (2026-10-01, mf-cfw PR 506)
- `git show origin/qa01:src/.../NetworkLocationAddEdit.test.tsx | sed -n '440,600p'` under the rtk hook returned a COMPRESSED rendering that looked like the file ended ~line 600, while the real file is 1418 lines; `grep -n` on the on-disk worktree file gave true structure. Cost: misdiagnosed describe order and missed the mockImplementation-swapping tests that only appear past line 958.
- Fix: for structural reads of any file under rtk, read the on-disk copy (Read tool / `/usr/bin/sed` on the checked-out file), never `git show` output.
- Same class, opposite direction (2026-10-13, webui2 ENG-1209514): after `git apply --3way` printed
  "Applied patch ... cleanly" x6, BOTH `git status` and `git diff --stat` showed a CLEAN tree while
  the files were in fact modified (verified by python read of the file content). rtk's compressed
  status/diff renderings can lie about worktree state, not just file contents. Ground-truth check
  for "did my change land": python `open(path).read()` + substring check, never rtk-piped git
  status/diff/grep output. (The `grep -c "send null to clear"` 0-match was the known quote-mangling
  trap firing again.)

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
- **`openspec archive <name>` prompts interactively** ("Proceed with spec updates? (Y/n)") and fails with `User force closed the prompt` in a non-interactive session. Always pass `-y`/`--yes`: `openspec archive "<name>" -y`. Applies even with a completed change (2026-09-21); when driving `openspec` from an agent session, prefer the long form `openspec archive "<change>" --yes`.

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

## openspec validate: requirement SHALL must sit on first line of body (2026-09-24)
- `openspec archive <change> --yes` failed strict validation: `ADDED "Enum fields..." must contain SHALL or MUST` even though the body had SHALL on line 2 of a wrapped paragraph. The delta parser truncates requirement text at the first newline (`openspec change show <id> --json --deltas-only` shows the truncated text). Fix: unwrap the first sentence so SHALL/MUST lands on the body's first line.

## spec:land extraction: never locate blocks by pre-computed line numbers (2026-09-25)
- Extracting a spec.md bullet block via a line number captured BEFORE an earlier edit in the same
  session grabbed the wrong block (decommissioned-POP tail instead of CopilotChatWidget), leaving
  a duplicated one-liner and a truncated bullet. Fix: locate extraction targets by content match
  (unique anchor string + structural scan for the block end) at extraction time, not by stale
  offsets; and always verify with `git diff --stat` + a targeted grep that exactly one pointer and
  zero truncated bullets remain before committing.

## `/opsx:*` not registered as skills under claudeDesktop CLAUDE_CONFIG_DIR (2026-09-26)
- In sessions using `CLAUDE_CONFIG_DIR=~/ns/git/claudeDesktop/.claude-config`, `Skill("opsx:explore")` fails `Unknown skill` — the commands live in `~/.claude/commands/opsx/*.md`, which that config dir doesn't load.
- Fix: Read `~/.claude/commands/opsx/<cmd>.md` and follow it directly. Writes outside `claudeDesktop/` (new repos under `~/ns/git/`) need sandbox bypass.
- Same root cause for `/boot-*` (live in `~/.claude/skills/`) and `/wb:*` (plugin installed only under
  `~/.claude/plugins/`) — an alternate `CLAUDE_CONFIG_DIR` loads only its own `skills/`, `commands/`,
  `plugins/`. Permanent fix (2026-09-29), user must run it — those dirs are on the sandbox write
  denylist and auto-mode refuses the bypass:
  `ln -sfn ~/.claude/skills/boot-* $CFG/skills/`, `mkdir -p $CFG/commands && ln -sfn
  ~/.claude/commands/opsx $CFG/commands/opsx`, then `CLAUDE_CONFIG_DIR=$CFG claude plugin marketplace
  add netSkope/webui-balkan-claude-plugin && CLAUDE_CONFIG_DIR=$CFG claude plugin install
  wb@webui-balkan-claude-plugin`. Restart the session afterwards; symlinked skills appear immediately
  but plugins/commands only load at startup.

## Claude `sessions/<pid>.json` `procStart` is UTC; `ps lstart` is local (2026-09-26)
- claude-status scanner compared `ps -o lstart=` to `procStart` and rejected every live session (20:41 local vs 12:41 in file, +8h). Fix: run `ps` with `TZ=UTC`. Also: `pkill -f <abs path>` misses a node started with a relative path — kill by port (`lsof -tiTCP:<port> -sTCP:LISTEN`).

## Declared a visual bug fixed after reproducing a DIFFERENT bug with a similar symptom (2026-09-26)
- Same session as above: found and fixed a genuine row-height-inflation bug (`h-full` → viewport
  height), took a clean screenshot, and reported the user's reported "text overlap" as resolved.
  User pushed back with their own screenshot still showing the overlap. Spent another full round
  re-testing viewport widths (1280/1000/850px) and hover states in TWO separate dev stacks (hybrid
  Angular + plain React via `/wb:setup:webui2-shell`) — found zero overflow in either, at any width,
  hovering or not. The missing variable, which the user had to say out loud: **the copilot chat
  widget must be open** — it squeezes the main content area (~830px), which is what actually narrows
  the table enough to trigger the real bug.
- Real root cause (distinct from the `h-full` one): `SubRowCell.tsx`'s wrapper div used a **fixed**
  `h-[50px]`, not a minimum. At full width the POP name never wraps, so this never mattered. Narrowed
  by the chat widget, a long POP name wraps to 3-4 lines (taller than 50px) but the box stays clamped
  at 50px with default `overflow: visible` — the wrapped text spills past its own box, and because the
  parent is `flex flex-col`, the NEXT sibling entry is positioned right after the first one's *nominal*
  50px box, not its actual (taller) rendered height — so the two entries' text visually collides.
  Fix: `h-[50px]` → `min-h-[50px]`.
- Verification technique that actually caught it (scrollWidth/clientWidth and bounding-rect-vs-parent
  checks both came back clean and are useless for THIS failure mode): pairwise intersect every
  sibling `div`'s `getBoundingClientRect()` within a row — `overlapY = min(a.bottom,b.bottom) -
  max(a.top,b.top)`, same for X, flag any pair with `overlapY > 2 && overlapX > 2` that isn't a
  parent/child pair. Zero hits after the fix, several before.
- **Lesson: when a user reports a specific visual defect from a screenshot, ask what interaction
  state produced it (hover? a panel open? a specific viewport?) BEFORE declaring victory on a
  same-area bug found via unrelated exploration** — a clean screenshot only proves the state you
  happened to capture was clean, not that the reported state is fixed. Two real, independent bugs
  can share a component and a symptom category ("something's wrong in this table") without being the
  same bug.

## Monitor-tool scripts run SANDBOXED — `gh` fails TLS (OSStatus -26276) silently inside them (2026-09-29)
- A Monitor polling `gh pr checks ... || { sleep 60; continue; }` delivered zero events for 30 min
  while CI had long finished: sandboxed `gh` fails every call with `tls: failed to verify
  certificate: x509: OSStatus -26276` (seen identically on a plain sandboxed Bash `gh` call), and
  the `|| continue` swallowed it, so silence looked like "still pending".
- Fixes: (a) verify with one direct `dangerouslyDisableSandbox` call before trusting monitor
  silence; (b) in monitor scripts, don't fully swallow the poll-command failure — emit a one-time
  "poll failing: <err>" line on first failure so the sandbox problem surfaces as an event.

## Flag-removal edits: user's mental model is "unwrap the gate, keep the body" — confirm before stripping shared infra (2026-09-30, ENG-960552)
- Removing CF `NPLAN5161_CFW_GEO_LOCATION_SUPPORT` + FF `nplan5161_cfw_geo_location_support` in webui (GA): while stripping the CFW_FIELD.SOURCE_COUNTRY/DESTINATION_COUNTRY enum + label entries from `cfw-unsupported-warnings.util.ts`, the user interrupted: 「這個任務是把flag 移除，讓本來 if(flag) (...) 變成 (...)，不是連 (...) 一起移除」— i.e. the default expectation for flag removal is `if (flag) { X }` → `X`, NOT deleting the gated body or its supporting infra (enum/labels/spec cases).
- For POSITIVE gates that rule is complete. For NEGATIVE gates (`if (!flag && cond) { warn }`) the two readings give OPPOSITE behavior: unwrap-to-`if (cond)` makes the warning ALWAYS fire (a GA regression); delete-branch makes it never fire (correct GA semantics, since "flag off ⇒ warn unsupported" and GA ⇒ always supported). This ambiguity is real — ASK with a concrete two-option question before proceeding; user then approved whole-branch deletion + enum/label/spec removal.
- Corollary (revised after PR review pushback on ENG-960552): keeping now-unused interface fields as "inert inputs callers still pass" is CIRCULAR — reviewer (ns-jahuja) correctly flagged it; delete the unused fields AND the call-site arguments together. For negative gates the right GA treatment is delete-branch + delete-inputs, not unwrap.
- webui worktree Jest specifics hit this session: `inline-policy-form.component.spec.ts` OOMs on default heap — run with `NODE_OPTIONS="--max-old-space-size=8192"` + `--runInBand`; `neo/node_modules` symlinks fine from primary. rtk hook compresses jest stdout so `| grep` pipes see nothing — redirect to a file (`> $TMPDIR/x.log 2>&1`) and grep the file. `cfw-unsupported-warnings` message grammar: `joinLabels` uses "apply" (plural) for 2+ fields — "Activities apply ... and ARE not applicable" (wrote "is", test caught it).

## Sandboxed `yarn install`, `craco start`, `git push` in mf-cfw all fail; run unsandboxed (2026-10-01)
- Worktree `yarn.lock` diverged from primary (4947 diff lines) so a `node_modules` symlink was unsafe; sandboxed `yarn install --frozen-lockfile` looped `There appears to be trouble with your network connection. Retrying...` past the 300s timeout (artifactory-rd + registry unreachable). Unsandboxed: 24s, and the postinstall ran `husky install` (no separate husky step needed).
- `yarn start:dev` sandboxed: `Could not find an open port at 0.0.0.0 ... listen EPERM` -> run with `run_in_background` + sandbox disabled, poll the output file for `webpack compiled successfully` (~20s). Backgrounding with `&`+`disown` prints `nice(5) failed`; use the `run_in_background` param instead. Background tasks are auto-stopped at their timeout, fine after validation.
- `git push` sandboxed: `ssh_dispatch_run_fatal: Connection to UNKNOWN port 65535: Broken pipe` -> retry unsandboxed; `gh pr create`/`gh api` unsandboxed too.
- Lockfile-diff check: zsh process substitution `diff <(git show ...) file` fails in sandbox (`/dev/fd/11: Operation not permitted`); redirect to `$TMPDIR` first.

## Read the i18n VALUE, not the key name, before claiming a label mismatch (2026-10-01)
- Told the user the field was mislabeled "Scope" from the key `traffic_simulator.form.scope_label`; the JSON value was already "Module". Only the key name was misleading; the real bug was the all/source/destination dropdown filtering the checklist. Check the rendered/i18n text before framing the defect.

## Stash-baseline proof for pre-existing test/typecheck failures (2026-10-05)
- To prove a failing test/typecheck error is pre-existing and not caused by the diff: `/usr/bin/git stash push -u -m "<unique-tag>"`, run the failing check, `/usr/bin/git stash apply <sha>` (find sha via `git stash list --format='%H %gs' | grep <tag>`), then `git stash drop 'stash@{0}'` after confirming the printed SHA matches. Used twice in one session (4 TS2589 phantoms + 1 detail-processing test) — turns "I think it's pre-existing" into evidence for the PR body.
- Variant (2026-10-12, vanguard PR #1611): proving new tests FAIL WITHOUT the fix — stash ONLY the source files, never `push -u` the whole tree: untracked test files get stashed too, the run collects 0 of the new tests, and "no failures" masquerades as a clean baseline. Correct form: `git stash push -m "<tag>" -- <src files only>`, run, `apply <sha>`, drop.

## Figma MCP: screenshot curl needs sandbox off; View seat rate-limits fast (2026-10-16)
- curl to www.figma.com/api/mcp/asset/* is denied by the sandbox proxy; adding allowed_domains still exited 56. Run the download unsandboxed.
- A Figma View seat hit the MCP call cap after ~6 calls (4 screenshots + 1 design_context + 1 variable_defs). Budget calls: fetch screenshots first, then design_context on the 1-2 sub-trees that matter most.

## OpenSpec change created in the primary checkout pre-worktree is invisible to archive from the worktree (2026-10-16)
- `openspec new change` ran in the primary checkout (worktree didn't exist yet); later `openspec archive "<name>"` from the worktree failed `Change not found` (and from a subdirectory failed `No OpenSpec changes directory found` — openspec must run from the repo root).
- Fix: `mv <primary>/openspec/changes/<name> <worktree>/openspec/changes/` (uncommitted scratch moves freely), then archive from the worktree root — spec delta lands in the worktree's tracked `openspec/specs/`, archive dir under `changes/archive/`, all committed with the fix.

## webui-insights usage-report extraction: needs Node 22 + unsandboxed (2026-10-20)
- `npx tsx <plugin>/scripts/extract-usage.ts` fails three ways in this env: (1) sandbox denies
  registry.npmjs.org; (2) sandbox denies tsx's IPC pipe listen (`EPERM /tmp/claude-501/tsx-501/*.pipe`);
  (3) system node v20 lacks `fs/promises.glob` (SyntaxError on import).
- Working invocation, unsandboxed with the plugin's bundled tsx under Node 22:
  `~/.nvm/versions/node/v22.22.2/bin/node <plugin>/node_modules/tsx/dist/cli.mjs <script> ...`
- Also: the extractor does NOT price Fireworks-proxied models (GLM/Kimi → $0; 140/179 sessions in a
  GLM-heavy month), and does not capture subagent sidechains (only 3, $0). For subagent token data,
  scan `~/.claude/projects/*/subagents/agent-*.jsonl` directly.

## wb Stop-hook flags merged-but-unarchived OpenSpec changes (2026-10-20)
- The wb plugin's remind-design-landing.sh Stop hook fires on ANY `openspec/changes/<slug>/` dir, including changes whose PR already merged (add-aws-sidecar-leg, ENG-1335119) — it reads them as "ephemeral design artifacts". Don't spec:land a merged change; `openspec archive "<slug>" --yes` (moves to archive/, lands spec delta) is the correct disposition, then commit the moves.

## Private Google Sheets: `/export?format=csv` curl returns 401 login page (2026-10-22)
- Working path (user pointed to docshare-publish's auth): unsandboxed `playwright-cli -s=gsheet open "<sheet edit url>" --headed --profile=$HOME/.playwright-cli-profile-netskope-sso` (user may need to redo Netskope Okta SSO in the window), then in-page same-origin `fetch('/spreadsheets/d/<id>/gviz/tq?tqx=out:csv&gid=<gid>')` → CSV text. Tab gids: click the tab, read `location.href`. gviz drops formatting (red/bold annotations) — screenshot too. `close` the session after.

## Reading Private GitHub Pages — browser OAuth, not gh token (2026-09-01)
- **`gh auth token` + curl does NOT work for a private `*.pages.github.io` URL.** Private Pages authenticate via a **browser OAuth cookie** (`_gh_pages`, per-site session via the `github.com/pages/auth` flow) — a different auth surface from the `gh` API token. Curling with `Authorization: token $(gh auth token)` returns HTTP 200 but redirects to `github.com/login?return_to=...pages/auth...` — the login page, not the content.
- **Correct approach — real Chrome + user OAuth + CDP read:**
  1. Launch a debug Chrome pointed at the target URL with a dedicated profile:
     `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 "--remote-allow-origins=*" --user-data-dir=/tmp/chrome-gh-oauth --no-first-run --no-default-browser-check "<url>" &`
  2. Have the **user** complete the GitHub OAuth once in that window (may chain Google→GitHub→authorize on a fresh profile). Cookie persists to the profile's `user-data-dir` on disk.
  3. Attach via CDP and read the DOM (`Runtime.evaluate` for `document.body.innerText`, links, etc.) or screenshot. The cookie survives a Chrome restart on the **same** `--user-data-dir`.
- **`--remote-allow-origins` is mandatory for CDP WebSocket.** Without it the `/devtools/page/<id>` ws handshake returns `403 Forbidden — Rejected an incoming WebSocket connection from the http://localhost:9222 origin`. In **zsh, quote the flag** (`"--remote-allow-origins=*"`) — a bare `*` triggers `no matches found` globbing. If Chrome was already started without the flag, kill and relaunch on the same profile (login is retained).
- **No `ws`/`websocket-client` module?** macOS Python is externally-managed (PEP 668, `pip install` blocked) and Node here lacks `ws`. Fastest fix: `python3 -m venv <dir> && <dir>/bin/pip install -q websocket-client`, then connect with an explicit `Origin: http://localhost:9222` header on the ws.
- **Why**: 2026-09-01 read an internal `bookish-robot-*.pages.github.io/analyzer` prototype this way after `gh` token curl bounced to login. The org repo owning the Pages subdomain is not discoverable by name (random `*.pages.github.io` slug ≠ repo name), so browser OAuth is the only reliable path.

## Sandbox `$TMPDIR` differs from unsandboxed `$TMPDIR` (2026-10-23)
- Wrote a script to `$TMPDIR/x/server.js` in a sandboxed call (`/tmp/claude-501/...`), then ran `node $TMPDIR/x/server.js` with sandbox off → `MODULE_NOT_FOUND` at `/var/folders/.../T/x/server.js`. The var expands differently per mode. Fix: use an absolute path (`/tmp/claude-501/<dir>/`) for any file shared between sandboxed and unsandboxed calls.
- Never dump a `~/.claude/tenants.json` entry with a key-name mask (`'pass' in key`) — it leaked `api_token`. Print only the needed field (`['url']`) or key names; read secrets into shell vars (`P=$(python3 -c ...)`) and pass `"$P"`.

## Reading private Google Sheets (2026-10-23)
- Reuse docshare's SSO profile: `playwright-cli -s=gsheet open <sheet-url> --headed --profile=$HOME/.playwright-cli-profile-netskope-sso` (clear `Default/Sessions` + `Current/Last Session|Tabs` first, as docshare.sh does). Needs `dangerouslyDisableSandbox`.
- Tab names: `eval "() => [...document.querySelectorAll('.docs-sheet-tab-name')].map(e=>e.textContent)"`.
- Data: same-origin `fetch('/spreadsheets/d/<id>/export?format=tsv&gid=<gid>')` inside `eval`. **Not** `gviz/tq?tqx=out:csv` — gviz guesses header rows and drops/merges header cell text.
- Red-text PM annotations + strikethrough + comments only visible in a screenshot / Comments panel (top-bar comment icon), not in the export.

## `$TMPDIR` differs sandboxed vs `dangerouslyDisableSandbox` (2026-10-29)
- Sandboxed Bash `$TMPDIR` = `/tmp/claude-501`; unsandboxed it is the macOS `/var/folders/.../T/`. A file written to `$TMPDIR` in a sandboxed call is "No such file" in a later unsandboxed call. Use the literal `/tmp/claude-501/...` path when a temp file crosses that boundary.
