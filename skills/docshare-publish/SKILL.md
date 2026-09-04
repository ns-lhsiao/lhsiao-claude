---
name: docshare-publish
description: Publish, list, delete, or read HTML/PDF/Markdown files on docshare.netskope.com (TeamSkope Docs) - the internal Google-IAP-gated file/HTML sharing service. Use whenever the user asks to publish/share/upload a report, deck, HTML page, or other file internally, asks for a docshare.netskope.com link to something, OR pastes a docshare.netskope.com/<shortcode> URL and wants to read/view/summarize what's behind it. The file to publish is whatever the conversation is about (a just-generated report, a file the user points to, etc.) - infer it from context rather than assuming a fixed location. Do NOT fetch a docshare.netskope.com URL with WebFetch or bare curl - it is IAP-gated and will just return a Google login redirect; always go through this skill's `get` command instead.
allowed-tools:
  - Bash(*/docshare-publish/scripts/docshare.sh *)
---

# Publish to docshare.netskope.com

`docshare.netskope.com` ("TeamSkope Docs") is Netskope's internal file/HTML sharing
service, behind Google Identity-Aware Proxy. It serves each uploaded file at a short
URL (`/<shortcode>`). No public API, no CLI in the org - this skill wraps its plain
HTML form endpoints with curl.

## The one thing that matters: it's just curl

The upload page is a plain `POST /upload` multipart form (fields `file`, optional
`shortcode`). No CSRF token, no JS. So every operation is pure curl carrying one
IAP cookie. A browser is needed **only** to (re)capture that cookie via Google SSO.

## Where the script lives

The script is installed at one of these two paths, depending on whether the skill
came from the user-level directory or a project checkout:

```
~/.claude/skills/docshare-publish/scripts/docshare.sh
.claude/skills/docshare-publish/scripts/docshare.sh
```

Do not use a bare `scripts/docshare.sh` (relative paths break unless cwd is the
skill dir) - invoke one of the two full paths directly, e.g.:

```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh check
```

| Command | What it does |
|---|---|
| `publish <file> [shortcode]` | upload; prints the live `https://docshare.netskope.com/<shortcode>` URL |
| `list` | table: filename / shortcode / file-id |
| `delete <target>` | delete by shortcode or 20-char file id |
| `get <shortcode\|url> [outfile]` | fetch published content - stdout, or save to `outfile` |
| `check` | is the cookie still valid? |
| `login` | open headed browser; capture the cookie now if the profile is already authed (agent-safe, non-interactive) |
| `capture` | after you finish Google SSO in the open browser, extract the cookie (pairs with `login`) |
| `relogin` | interactive terminal only: open browser, pause for SSO, capture. Falls back to `login`+`capture` when there's no tty |

## Typical flow (publishing a file)

The examples below use the user-level path from the previous section. If the skill
was installed at the project-level path instead, substitute
`.claude/skills/docshare-publish/scripts/docshare.sh` throughout.

The file to publish is whatever the conversation is about - a report you just wrote,
a file the user names or points to, an export from another tool. There is no fixed
"artifacts folder"; figure out the right file from context, same as any other file
operation.

Run `check` first. If it reports no/expired cookie, authenticate with `login` - the
agent-friendly entry point. (`relogin` also works: it detects a missing tty and
degrades to the same `login`/`capture` flow, so it won't hang. `login` is just the
more direct call when you're driving this non-interactively.)

```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh check
```
```bash
# opens the headed browser; if the netskope-sso profile is already logged in, this
# captures the cookie and finishes on its own - no SSO, no Enter key.
~/.claude/skills/docshare-publish/scripts/docshare.sh login
```
If `login` reports the browser is open but not logged in, tell the user to complete
Google SSO in that window, wait for them, then run `capture`:
```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh capture
```
Then publish:
```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh publish /path/to/foo-report.html foo-report
# -> https://docshare.netskope.com/foo-report
```

### Naming the shortcode (do this every publish)

Always publish **with** an explicit shortcode - never let it auto-generate. Before
uploading:

1. Read the file (its `<title>`, top heading, or first paragraph for HTML; the H1 for
   Markdown) to understand what it is.
2. Propose a short, memorable, semantic shortcode: letters/numbers/hyphens only,
   kebab-case, no date prefix (the file already carries the date; the URL should read
   cleanly - `/release-risk-digest`, not `/2026-07-16-release-risk-digest`).
3. Show the user the proposed shortcode + URL and let them override in one line, then
   pass it explicitly: `publish <file> <shortcode>`.

Only fall back to omitting the shortcode (random 5-char code like `/2gua1`) if the user
explicitly wants a throwaway link. When omitted, the script resolves + prints the row so
you still get the URL.

## Reading a published doc

`get` accepts either a bare shortcode or a full URL, so paste whatever the user gave
you:

```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh get foo-report
~/.claude/skills/docshare-publish/scripts/docshare.sh get https://docshare.netskope.com/foo-report
```

That prints the raw file to stdout - fine for HTML/Markdown/text, which you can read
directly. **PDFs are binary** - never let a PDF hit stdout into your context. Pass an
`outfile` to save it, then read the saved file with the Read tool (which paginates
PDFs):

```bash
~/.claude/skills/docshare-publish/scripts/docshare.sh get some-deck /tmp/some-deck.pdf
```

`get` runs `check`'s same cookie-validity guard first, so an expired cookie fails with
the same "run login" message rather than silently returning Google's login page as if
it were the document.

`list` only shows files uploaded under your own account - it will not find someone
else's shortcode. For a doc someone else published, `get` (by shortcode or URL) is the
only path; there's no cross-account listing.

## Auth model (read before debugging a 302)

- Cookie lives in `~/.claude/connections/docshare.json` (mode 600), the same directory
  and convention as the jenkins/sumo/spinnaker skills. Shape:
  ```json
  { "host": "docshare.netskope.com", "cookie_header": "__Host-GCP_IAP_AUTH_TOKEN_=...; GCP_IAP_XSRF_NONCE_*=..." }
  ```
  The script strips an optional leading `Cookie:` and any stray newlines out of
  `cookie_header`. Override the path with `DOCSHARE_CONN_FILE` if needed.
- It's a **session-type** IAP token - Google expires it server-side after a while.
  When expired, every request 302-redirects to `accounts.google.com`. The script
  detects this and tells you to re-authenticate.
- Auth uses a **headed** playwright browser on the persistent profile
  `~/.playwright-cli-profile-netskope-sso`. Because that profile persists the Google
  session, the common case is that no SSO is needed at all - `login` opens the browser,
  sees it's already authed, and writes the connection file immediately. Only a genuinely
  expired profile needs a fresh SSO (`login` -> user does SSO -> `capture`).
- Cookie capture goes through `playwright-cli state-save`, which is sandboxed to a few
  allowed file roots. The script tries `./.playwright-cli/state.json` (cwd-relative,
  the usual default allowed root) FIRST, then `~/.claude/connections/docshare-state.json`,
  and deletes the state file immediately after extracting the docshare cookies - that
  file also holds cookies for every other logged-in site (Jira, Slack, ...), so it's
  never left behind.
- `relogin` is the interactive-terminal convenience (opens browser, waits on Enter,
  captures). It auto-detects a missing tty and degrades to the `login`/`capture` split,
  so an agent should just call `login` (and `capture` if prompted) directly.

## Endpoint reference (if the script breaks)

```
GET  /                       homepage: upload form + your files table
POST /upload                 multipart: file=@path;type=..., shortcode=<opt>
                             -> 303 redirect ?success=... | ?error=File+too+large (max 32MB)
GET  /<shortcode>            serve the published file
POST /files/<id>/delete      -> 303 ?success=File+deleted+successfully
GET  /files/<id>/edit        edit page (not wrapped; shortcode+content editable in UI)
```

File-id is a 20-char alphanumeric, distinct from the shortcode. `list` shows both.

## Overwriting / updating a published doc

Two options: `delete` then `publish` again with the same shortcode, or use the UI
`/files/<id>/edit` page. The script does not wrap edit - re-publishing is simpler for
regenerated artifacts.
