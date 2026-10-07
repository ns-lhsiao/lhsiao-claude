# Live agent prompt template

Fill every `{{...}}` from the page file (`pages/<slug>.md`) and the run arguments, then pass
the result as the sub-agent prompt. Do not leave placeholders. Credentials are inserted by the
orchestrator only inside this prompt; the agent must never write them anywhere.

---

You are running LIVE e2e regression probing of ONE page on a shared tenant and writing a
screenshot-backed HTML report. Report prose: Traditional Chinese (Taiwan) mixed with English
technical terms; short sentences.

## Target
Tenant: {{TENANT_URL}} | User: {{USER}} | Password: {{PASSWORD}}
(CLI only. NEVER write the password to any file, report, caption or log. Redact if it appears.)
Page: {{PAGE_TITLE}} — nav {{NAV_PATH}}, hash route `{{ROUTE}}`.
Expected renderer on this tenant: {{EXPECTED_RENDERER}} (flag evidence: {{FLAG_EVIDENCE}}).
Discriminators present: {{DISCRIMINATORS_PRESENT}}. Must be ABSENT: {{DISCRIMINATORS_ABSENT}}.
Assert the renderer FIRST. Mismatch => mark all cases BLOCKED and stop.

## Tooling (playwright-cli, headless; run EVERY call with dangerouslyDisableSandbox=true)
- Session name MUST be `{{SESSION}}`. Login: `playwright-cli -s={{SESSION}} open {{TENANT_URL}}/locallogin`,
  `snapshot`, `fill` Username/Password by ref, click `Log In`, poll `eval "() => location.hash"`
  until it is not `#/login...` (~20 s). Dismiss any welcome wizard.
- After login NEVER `open`/`goto` a hash URL. Navigate with
  `eval "() => { window.location.hash = '#/...'; }"` or by clicking nav. Loads take 30-60 s: poll
  a readiness selector, never guess with sleeps.
- SESSION TIMEOUT: the session dies after several idle minutes. If a snapshot suddenly shows
  nothing, screenshot first; if it says "session has timed out", log in again and re-read state.
  Never infer success from an empty snapshot.
- `run-code` page.route mocks must be registered in the SAME call as the navigation.
- Multi-line JS: write to /tmp/claude/{{SESSION}}/x.js then `eval "$(cat /tmp/claude/{{SESSION}}/x.js)"`.
- Screenshots: `screenshot --filename <path> [--full-page]`. Use /usr/bin/grep if rtk mangles grep.
- Leave the session open at the end.
- RBAC mock target for this page: {{RBAC_MOCK}}

## Safety rules (shared tenant)
{{SAFETY}}
- Create/edit/delete ONLY objects named `{{OBJECT_PREFIX}}<4 random chars>*`. Never touch others.
- Delete (or revert) everything you created; verify via {{VERIFY_CLEANUP}}; record final state.
- NEVER click Apply / Send for Approval / call deploy. If cleanup needs Apply, stop and report it.
- Real devices/users/clients are read-only.

## Test cases (screenshot each; PASS/FAIL/PARTIAL/BLOCKED/N-A honestly; failures stated plainly;
## retry at most once and say so). Compare each result with `baseline` and flag deviations.
{{CASE_TABLE}}

## Open questions to answer with live evidence
{{OPEN_QUESTIONS}}

## Output (REQUIRED)
- `{{PROJECT_DIR}}/{{SLUG}}.html` (mkdir -p; sandbox disabled). Screenshots
  `{{PROJECT_DIR}}/screenshots/{{SLUG}}/<CASE-ID>-<slug>.png`, referenced with RELATIVE
  `<img src="screenshots/{{SLUG}}/...">` inside `<figure class="shot"><figcaption>`.
- Copy the dark-GitHub `<style>` block verbatim from {{STYLE_SOURCE}}.
- Sections: H1+sub, meta chips (tenant, date, renderer, flag evidence), Summary table
  (ID | case | priority | result | screenshot), per-case cards, Findings, Cleanup state,
  Environment/limits.
- `{{PROJECT_DIR}}/results/{{SLUG}}.json`: `{"run":{...},"cases":{"<ID>":{"title","result","screenshot","note"}}}`.
- Do NOT edit all-html/index.html.
- Return <= 250 words: counts, top findings, deviations from baseline, report path, cleanup confirmation.
