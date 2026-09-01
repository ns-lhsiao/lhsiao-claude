---
name: mockup-api-mapping
description: >-
  Produces an HTML report that numbers every element of a UI mockup screenshot
  (Figma frame, Confluence-attached prototype image, or live-tenant Playwright
  capture) and checks it against the real API spec (OpenAPI/Swagger, embedded
  in Confluence or a raw file) - green circle + citation if the field exists,
  red circle + explanation if it's a gap. Output matches the existing
  all-html/<project>/figma-vs-spec-*.html report style. Triggers on "annotate
  this mockup against the API spec", "figma vs API mapping report", "UI mockup
  API field mapping", "screenshot spec diff", "mark up this screenshot with
  API fields", or requests to compare a design mockup's fields to a backend
  schema.
---

# Mockup ↔ API Field Mapping

Turns "does this Figma/prototype screen actually match what the API returns?"
into a numbered, cited, green/red annotated report — not a prose guess.

## When to use this

- User has a UI mockup (Figma frame, a Confluence-attached prototype
  screenshot, or a live-tenant Playwright capture) and an API spec, and wants
  to know which visible UI elements have a real backing field and which don't.
- Any "check the Figma against the spec" / "make sure this mockup matches the
  API" request for a design doc still in progress.
- Do NOT use this for reviewing already-shipped code against a spec (that's a
  contract-verification job — see `contract-probe`/`add-contract-tests`
  instead). This skill is for **mockup vs. spec**, before code exists.

## Inputs required before starting

1. **The API spec.** Ask for it if not given. Common sources, in order of how
   often they show up:
   - A Confluence page using the `swagger-open-api-macro` — the *entire* OpenAPI
     YAML/JSON lives inline inside a `<![CDATA[...]]>` block in that macro's
     `body.storage.value`. No GitHub access needed. Extract with:
     ```python
     import json, re
     body = <fetched via Confluence REST API, expand=body.storage>
     m = re.search(r'<!\[CDATA\[(.*?)\]\]>', body, re.DOTALL)
     yaml_text = m.group(1)
     ```
     If the design doc only links to the spec by title (`ri:content-title`),
     resolve it via `GET /wiki/rest/api/content?title=<title>&spaceKey=<key>`
     first (see `confluence-reader`/`confluence-updater` skills for auth setup).
   - A raw `.yaml`/`.json` file in a repo (read directly).
   - A GitHub-hosted spec — only reach for this if the above two don't apply;
     flag to the user up front that GH access might be needed, and offer to
     proceed with whatever's locally readable first (mirrors the real session
     that motivated this skill — the spec turned out to be embedded in
     Confluence, no GH needed at all).
   Once extracted, grep for the path/schema names you need
   (`grep -n "^  /\|^    <Namespace>\."`) rather than reading the whole file
   into context if it's large.

2. **The UI mockup screenshot(s).** Common sources:
   - **Figma.** Load `skill://figma/figma-use/SKILL.md` guidance is NOT required
     for read-only metadata/screenshot calls (only `use_figma` needs it). Use
     `mcp__figma__get_metadata` (fileKey + nodeId from the Figma URL) to see the
     frame tree and find sub-node IDs for individual screens/dropdowns, then
     `mcp__figma__get_screenshot` per node. Download the returned short-lived
     URL with `curl -sL -o <path> "<url>"` immediately — it expires.
   - **Confluence attachments.** List via
     `GET /wiki/rest/api/content/{pageId}/child/attachment`, download via the
     `_links.download` path on the same base URL with Basic auth.
   - **Live tenant.** Only if the mockup doesn't exist yet or you need to
     confirm real behavior — follow the `boot-playwright` skill's guardrails
     (confirm a testable target/tenant with the user FIRST, never guess
     credentials or tenant, never write credentials into the report).
   - Get one screenshot per meaningful screen/state, not one giant scroll — a
     dropdown menu's option list is its own screenshot, not a crop of the main
     view.

## Workflow

### 1. Read the spec fields for the screen(s) in scope

For each schema/endpoint relevant to the mockup, read the actual
`description`/`enum`/`type` for every property — don't infer field names from
memory or from an *adjacent* legacy form. Spec authors sometimes write the
mapping for you (e.g. a property description literally saying `Maps to the
WebUI's "X" criteria` — when present, that phrase is authoritative, use it
verbatim rather than re-deriving the mapping yourself).

Watch for a common trap: an unrelated legacy UI (e.g. a full policy-editing
form) may share *some* field names with the new API but at a different
cardinality (single value vs. array) or a smaller field set (a "simulate one
sample" API is usually much smaller than a "define all match criteria" form).
Don't assume the legacy form's full field list carries over — verify each one
against the actual new spec.

### 2. Map each visible UI element to a field (or confirm it's a gap)

Walk the screenshot top-to-bottom, left-to-right. For each interactive element
or displayed value, decide:
- **Confirmed** — cite the exact schema + property + line number (or clear
  section reference if no stable line numbers exist).
- **Gap** — state plainly that no field carries this. Don't soften a real gap
  into "TBD" or "needs confirmation" if you've actually read the full schema
  and it's absent — say "confirmed absent," not "unconfirmed."
- **Partial/derived** — the closest field exists but doesn't cover the exact
  UI semantic (e.g. a total count exists but not a "current index into a
  paginated list of items" the UI shows) — call out precisely what's covered
  and what still isn't.

Flag anything surprising immediately, even if not directly asked:
enum/cardinality mismatches, a UI control requiring data that would need
cross-referencing *other* response arrays (not just the one the element lives
in — this is a common real gap, not a hypothetical), or copy typos in the
mockup worth flagging to design.

### 3. Annotate the screenshot(s)

Use `scripts/annotate.py` (`mark_points()`) from this skill directory — don't
rewrite the marker-drawing logic from scratch each time.

```python
import sys
sys.path.insert(0, "<path to this skill>/scripts")
from annotate import mark_points, composite_side_by_side
from PIL import Image

img = Image.open("raw-screenshot.png").convert("RGB")
points = [
    # (x, y_top, number, confirmed)
    (285, 614, 1, True),
    (285, 978, 2, False),
]
mark_points(img, points)
img.save("ANNOTATED-01-screen.png")
```

Coordinate-finding loop (budget at least one correction pass, first guesses
are frequently wrong):
1. Read the raw screenshot with the Read tool, eyeball approximate (x, y) for
   each element.
2. Render, then **Read the annotated output back** before using it anywhere.
3. Common failure modes to check for: markers landing on a left-nav sidebar
   instead of the content pane (screenshot includes both — use an x past the
   nav's right edge), two markers at the same (x,y) band from adjacent
   multi-column layouts colliding (give side-by-side content extra x
   separation, ≥50px), or a marker sitting on the wrong row because of an
   off-by-one row-height assumption.
4. If a screenshot has a **pre-existing annotation already on it** (e.g. a
   designer's own note bubble in the Figma file), do not silently let your
   numbered markers look like they include it — call it out explicitly in the
   report caption so it isn't mistaken for one of your callouts.
5. It's fine to ship with approximate-but-close positioning — a caption noting
   "marker positions approximate, see legend table for the authoritative
   mapping" is an acceptable tradeoff against spending unbounded time on
   pixel-perfect placement. The legend table is the source of truth; the
   markers are a navigation aid.

For a mockup split across multiple small crops that belong in one figure (e.g.
two separate dropdown-menu screenshots), use `composite_side_by_side()` to
paste them together with enough gap for markers, rather than fighting to place
markers on two separate `<img>` tags in the report.

### 4. Write the report

One HTML file per logical unit of the mockup (e.g. one for each major flow —
mirrors how this skill's motivating session produced `figma-vs-spec-simulate.html`
and `figma-vs-spec-analyze.html` as two separate reports rather than one giant
file). Reuse this exact style block (dark GitHub theme, consistent with other
reports in the project):

```html
<style>
  :root{
    --bg:#0d1117; --card:#161b22; --border:#30363d; --accent:#58a6ff;
    --green:#3fb950; --red:#f85149; --yellow:#d29922; --muted:#8b949e;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:#c9d1d9;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:24px;margin:0 0 4px}
  .sub{color:var(--muted);margin:0 0 20px}
  .meta{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:28px}
  .chip{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:3px 12px;font-size:12px;color:var(--muted)}
  h2{font-size:16px;margin:36px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
  table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:8px}
  th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
  th{background:#1c2128;color:var(--muted);font-weight:600;font-size:12px}
  tr:last-child td{border-bottom:0}
  code{font:12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;background:#1c2128;border:1px solid var(--border);border-radius:4px;padding:2px 5px;color:var(--accent)}
  .gap{color:var(--red);font-weight:600}
  .ok{color:var(--green);font-weight:600}
  .num{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:700;margin-right:4px}
  .num.g{border:2px solid var(--green);color:var(--green);background:rgba(63,185,80,.12)}
  .num.r{border:2px solid var(--red);color:var(--red);background:rgba(248,81,73,.12)}
  .note{border-left:3px solid var(--yellow);background:rgba(210,153,34,.08);padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0;color:#e3d3a8}
  figure{margin:16px 0;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px}
  figure img{width:100%;border-radius:4px;display:block;background:#fff}
  figcaption{color:var(--muted);font-size:12px;margin-top:8px}
  .legend{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0 20px;font-size:12px;color:var(--muted)}
  .legend span{display:inline-flex;align-items:center;gap:6px}
</style>
```

Structure per report:
- H1 + one-line sub-title stating exactly what's in/out of scope (mirror any
  explicit scoping the user gave you — e.g. "only the X sidepanel, not Y").
- Meta chips: ticket/project, component name, spec source, screenshot source,
  date.
- A `.legend` line explaining the ✓/✕ marker convention once, up top.
- One `<h2>` section per screenshot: the annotated `<figure>` with a caption
  covering approximation caveats and any pre-existing-annotation warning, then
  a legend `<table>` (# | UI element | spec field/path + type | status +
  citation).
- A closing **Summary** table: confirmed/gap counts per section, plus a
  `.note` callout for the single most consequential finding (not every gap
  deserves equal weight — call out the one that changes what someone should
  build next, the way the earlier session's "cross-array reverse-index"
  finding did).

### 5. Publish

Per the project's HTML Reports convention (check the relevant CLAUDE.md if this
skill is running in a session that has one):
- Write to `all-html/<project>/<name>.html`, screenshots into an adjacent
  `screenshots/` subfolder (never reference a `/tmp` path from the final HTML).
- Update `all-html/index.html`: bump the project's `(N)` count, add a new
  `<li>` with `data-tags`, a plain-text `.snippet` (~160 chars, drawn from the
  report's own findings), and 2-4 `.tags` chips — reuse `design-review`,
  `api-mapping`, `validation` if they fit; only invent a new tag class if none
  do, and add its CSS rule in the same turn.

## What NOT to do

- Don't guess field names from a similar-but-different UI when the real spec
  is available — always resolve to the actual spec text.
- Don't downgrade a confirmed-absent field to "TBD"/"needs confirmation" — say
  what you actually found.
- Don't skip the "read the annotated image back" step — misplaced markers
  (wrong column, overlapping text, colliding with a pre-existing design note)
  are the single most common failure mode of this workflow and are cheap to
  catch before shipping.
- Don't produce one wall-of-markers screenshot when the mockup has clearly
  distinct sub-screens (input form vs. results vs. history) — split into
  multiple figures/sections so each stays legible.
