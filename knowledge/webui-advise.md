# webui Validation Advice (boot-bugfix / boot-feature)

Applies when a `/boot-bugfix` or `/boot-feature` change's scope touches **webui**
(`src/webui/...`). Split validation evidence by which side of the stack changed.

## Angular / React side

If the change touches Angular (webui neo) or React (mf-client, mf-cfw, webui2 Balkan
hybrid), Playwright screenshot evidence is REQUIRED — no exceptions. Delegate to
`/boot-playwright <recipe> <slug>` per the recipe table already in `boot-bugfix`
Phase 5 / `boot-feature` Step 3.5. Do not substitute curl evidence for a frontend
change; the renderer-mount risk in [[webui2-testing]] (legacy Angular vs React) can
only be caught by actually driving the browser.

## PHP side

If the change touches a PHP controller/model/helper, attach curl request/response
evidence for the exercised endpoint(s) — full request (method, URL, headers, body)
and full response (status, headers, body), not a truncated excerpt.

**CSRF for curl-driven validation**: webui PHP controllers reject session-less curl
calls at the CSRF check before they ever reach the code under test. To capture
evidence, temporarily comment out (mark out) the CSRF check for the specific
controller/route under test, run the curl calls, capture the evidence, then
**immediately revert the comment-out** before doing anything else.

Guardrails — non-negotiable:
- Local/dev checkout only. Never do this against a shared, staging, or prod
  environment.
- The CSRF disable must never appear in the diff handed to `/opsx:apply` output,
  the commit, or the PR. Before Phase 8 commit, run `git diff` over the touched
  PHP files and confirm the CSRF check is back to original — treat any residual
  diff on that check as a blocking failure, same severity as a failed test.
- If the CSRF check can be satisfied instead by a legitimate token round-trip
  (GET the page/endpoint that issues the token, then pass it in the follow-up
  curl call), prefer that over disabling the check — reserve the mark-out for
  cases where the token round-trip itself isn't the thing under test.
- Do not extend this practice to non-validation contexts (e.g. shipping a
  "test bypass" flag in product code). This is throwaway, local, and reverted
  every time.
