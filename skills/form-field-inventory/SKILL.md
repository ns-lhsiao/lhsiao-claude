---
name: form-field-inventory
description: >-
  Generates a markdown inventory of all form fields for a given UI component,
  page, or tab. For each field, outputs: field name, form control type, the
  corresponding API/endpoint payload property (if any), and the feature flag(s)
  that gate its visibility. Also audits wiring (parser/builder/UI connectivity),
  detects dead fields, and cross-checks condition gates against v1 legacy source.
  Triggers on "list form fields", "field inventory", "what fields does X have",
  "wiring audit", or requests to document a component's form surface.
argument-hint: "<component path | page name | tab name>"
user-invocable: true
---

# Form Field Inventory

**Emit "Skill activated: form-field-inventory"**

Generate a structured markdown table documenting every form field in a target
UI component, page, or tab.

## Context

$ARGUMENTS

---

## PHASE 1: Locate the Target

Parse `$ARGUMENTS` to identify the target. It may be:

| Input Form | Example | Action |
|------------|---------|--------|
| File path | `src/features/client/.../*.tsx` | Read the file directly |
| Component name | `ClientSettingsTab` | Search for the component in the codebase |
| Tab/page name | `Install & Troubleshoot` | Find the tab within its parent page/modal |
| Angular template ref | `#installTroubleshoot` | Locate the ng-template in the HTML |

If the target is ambiguous, ask the user to clarify.

## PHASE 2: Analyze Form Fields

For each form field found in the target, extract:

1. **Field name** - The user-visible label or closest identifier
2. **Control type** - checkbox, dropdown, text input, number input, radio, multi-select, time picker, toggle, textarea, file upload, etc.
3. **Form model** - The variable, FormControl, or state binding (e.g., `clientAllowAutoUpdate`, `goldenVersionFormControl`)
4. **Payload property** - The key name sent to the API on save (if identifiable from the submit/save handler). Use `-` if the field does not map to a payload property or if the mapping is not determinable.
5. **Feature flag(s)** - The flag(s) that gate this field's visibility. Use `none` if always visible. If nested under a parent field's condition (e.g., "only when auto-update is enabled"), note the parent dependency too.

### How to find payload properties

- Trace from the submit/save handler to see how the form model value flows into the request body.
- For Angular: look at the `submit()` or `save*()` method that constructs the `data` object.
- For React: look at the payload builder or mutation call.
- If the field is purely UI-local (e.g., a collapse toggle, tab selector), mark payload as `-`.

### How to identify feature flags

- Look for `*ngIf`, conditional rendering (`&&`), `[hidden]`, `[disabled]` guards.
- Trace the guard variable back to its source (e.g., `NsConstants.X`, `useFlag('x')`).
- Distinguish between:
  - **Visibility flags** - field is not rendered at all without the flag
  - **Parent dependencies** - field renders only when a parent toggle is enabled (note as `parent: fieldName`)

## PHASE 2.5: Wiring Audit

For each form field identified in Phase 2, verify it is connected end-to-end by
checking three layers:

1. **Parser** - Is the field populated from the API response (GET), or hardcoded
   to a default? Search the payload parser / form initializer.
2. **Builder** - Is the field emitted in the payload on save (POST/PATCH)? Search
   the payload builder / submit handler.
3. **UI** - Is the field rendered as an interactive control?

A field is **dead** if it's rendered in the UI but missing from either the parser
or builder (toggling it does nothing on save). A field is **orphaned** if it exists
in the form types but isn't rendered.

Output a `## Wiring Gaps` table when any issues are found:

```markdown
## Wiring Gaps

| Form Model | Parser | Builder | UI | Verdict |
|---|---|---|---|---|
| `enableDeviceClassificationNotifications` | hardcoded `false` | absent | rendered | dead field (duplicate of `uploadDeviceInfo`) |
| `allowUserRestart` | hardcoded `false` | absent | rendered | dead field (out of scope) |
```

- `present` = field is read from API response or emitted in payload
- `hardcoded` = always set to a fixed default, never from API
- `absent` = not referenced at all
- `rendered` / `not rendered` for UI

### Condition Gate Cross-Check

For each field that has a feature-flag gate in the source (v1 legacy or design
doc), verify the v2 implementation checks the equivalent flag. Common failure
modes:

- v1 has `flag: X + parent: Y`, v2 only has `parent: Y` (missing flag gate)
- v1 has `flag: X`, v2 has the flag in the hook but never references it in JSX

Output a `## Condition Gate Mismatches` table when discrepancies exist:

```markdown
## Condition Gate Mismatches

| Field | Expected Condition | Actual Condition | Gap |
|-------|-------------------|-----------------|-----|
| Enable 64-bit | flag: `win64Support` + parent: autoUpdateEnabled | parent: autoUpdateEnabled only | missing flag gate |
```

## PHASE 2.6: v1 Mapping (Optional)

When the user provides a v1 source (Angular template, legacy inventory, or file
path) alongside the v2 target, generate a cross-mapping table:

```markdown
## v1 -> v2 Field Mapping

| # | v1 Field | v1 Payload | v2 Form Model | v2 Payload | v2 Condition | Status |
|---|----------|-----------|---------------|------------|--------------|--------|
| 1 | ... | ... | ... | ... | ... | wired / dead / out of scope |
```

Status values:
- `wired` - fully connected end-to-end in v2
- `dead` - exists in v2 form types but not wired to parser/builder
- `out of scope` - explicitly excluded from the current migration (cite the NPLAN)
- `missing` - v1 field has no v2 counterpart and is not documented as out of scope

This phase is skipped when no v1 reference is provided.

## PHASE 3: Output

Write the result as a markdown file with this structure:

```markdown
# Form Field Inventory: {Target Name}

> Source: `{file path}`
> Generated: {date}

## Fields

| # | Field | Control | Form Model | Payload Property | Condition |
|---|-------|---------|------------|------------------|-----------|
| 1 | ... | ... | ... | ... | ... |

## Feature Flags Referenced

| Flag | Source | Purpose |
|------|--------|---------|
| `flag_name` | `NsConstants.x` / `useFlag('x')` | Gates field Y |

## Notes

- {Any non-obvious mappings, legacy quirks, or conditional logic worth calling out}
```

### Condition column format

- `none` - always visible
- `flag: flag_name` - gated by a feature flag
- `parent: fieldName` - visible only when parent field is enabled
- `flag: flag_name + parent: fieldName` - both conditions apply

## Output Location

Write the markdown file to the **same directory** as the target source file, named
`formFields.md`. If the target is a tab within a larger component, write it adjacent
to that component's directory or inside it (prefer the most specific directory).

Examples:
- Target: `src/features/client/client-configuration/components/ConfigModal/ClientSettingsTab.tsx`
  Output: `src/features/client/client-configuration/components/ConfigModal/ClientSettingsTab.formFields.md`
- Target: Angular tab `#installTroubleshoot` inside `config-modal/`
  Output: `config-modal/install-troubleshoot.formFields.md`

After writing the file, print the path to the user.

## Rules

- Read the source code. Do not guess or hallucinate field names.
- If the target spans multiple files (e.g., a tab component that imports sub-components), follow the imports.
- Include fields inside collapsible/advanced sections - note them with "(Advanced)" suffix in the Field column.
- Omit purely structural elements (dividers, headings, info banners) - only document interactive form controls.
- If a field has validation constraints worth noting, add them in the Notes section.
- Output the table sorted by visual order in the UI (top to bottom, left to right).
- Always write the result to a file. Do not only print to stdout.
