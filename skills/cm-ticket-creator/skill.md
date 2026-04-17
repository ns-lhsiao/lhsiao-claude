---
name: cm-ticket-creator
description: Create CM (Change Management) Operational Change tickets in Jira for feature flag enablement, config changes, or other operational changes on production datacenters. Use when users mention "create CM ticket", "CM for flag", "change management ticket", or need to enable/disable a feature flag or config for a tenant on a specific POP.
---

# CM Ticket Creator

Create Operational Change tickets in the CM (Change Management) Jira project for production config changes — most commonly enabling or disabling a feature flag for a specific tenant via the provisioner API.

## When to Use This Skill

- User wants to create a CM ticket to enable/disable a feature flag
- User wants to create a CM for a config change on a production datacenter
- User mentions "create CM", "CM ticket", "change management" for an operational change
- User references an existing CM ticket as a template

## Project Metadata

| Field | Value |
|-------|-------|
| Project | CM (key: `CM`, id: `12692`) |
| Issue Type | Operational Change (id: `15980`) |
| Default Priority | Major (id: `3`) |

## Workflow

### Step 1: Gather Context

Extract the following from the user's request. If any required field is missing or ambiguous, ask before proceeding.

**Required:**

| Input | Description | Example |
|-------|-------------|---------|
| `flag_name` | The feature flag or config key to change | `flag_nplan5196_enforce_enrollment_feature_enabled` |
| `tenant_id` | Numeric tenant ID | `25491` |
| `tenant_url` | Tenant hostname | `soscv.goskope.com` |
| `datacenter` | POP code where the tenant is homed | `FRA2` |
| `eng_ticket` | The upstream ENG ticket driving this change | `ENG-975879` |

**Optional (inferred or defaulted):**

| Input | Default | Description |
|-------|---------|-------------|
| `new_value` | `1` | Value to set (usually `"1"` to enable, `"0"` to disable) |
| `old_value` | `0` | Expected current value (for pre-check) |
| `description_text` | Inferred from flag name | What the change does for the customer |
| `schedule` | Next available maintenance window for the DC's region | Requested begin/end dates |

If the user references an existing CM ticket as a template, fetch it via REST API and adapt its structure.

If the user references an ENG ticket, fetch it to extract tenant info, datacenter, and context.

### Step 2: Resolve Datacenter IDs

Look up both datacenter field option IDs from `references/datacenters.md`:
- `customfield_17280` (Datacenters)
- `customfield_27178` (Impacted Datacenters)

Derive the namespace using the pattern: `<dc_lowercase>-mp-prod--webui` (e.g., `fra2-mp-prod--webui`).

**Important:** Always confirm namespace with the user if the datacenter is unfamiliar. See LEARNINGS.md for namespace conventions.

### Step 3: Draft Ticket

Build the following fields:

**Summary:** `Enable <flag_name> for tenant <tenant_id> (<tenant_url>) in <DC>`

(If disabling, use "Disable" instead of "Enable".)

**Description (ADF):**

```
Enable flag `<flag_name>` in <DC> for tenant id <tenant_id> (`<tenant_url>`).

Requested via <eng_ticket>.
```

**Maintenance Outline (`customfield_17224`):**

```
## Enable flag <flag_name> in <DC> for tenant id <tenant_id> (<tenant_url>)

Use kubectl to exec into a webui pod in <DC> and run the provisioner API commands below to check the current state, enable the flag, verify, and roll back if needed.
```

**Pre-maintenance Tasks (`customfield_17225`):**

```
You only need to run this from one webui pod in <DC>.

Before every step get inside the webui pods through kubectl in Rancher for <DC>:
- Login to Rancher
- Find <DC> namespace (<namespace>)
- Open kubectl Shell:

    kubectl get pods -A | grep webui-webui
    kubectl exec -it -n <namespace> <pod name> -- /bin/bash

Then check the current status of the flag:

    curl -H 'Content-Type: application/json' "http://provisioner-pycore-provisioner-tm/client/config?tenantid=<tenant_id>" | jq -r '.data.<flag_name>';

Expected response: <old_value>
```

**Maintenance Tasks (`customfield_17226`):**

```
Repeat the same steps in the pre-maintenance section to get inside the <namespace> pods, then run this command to turn the flag on:

    curl -X POST -H 'Content-Type: application/json' -d '{ "<flag_name>": "<new_value>"}' "http://provisioner-pycore-provisioner-tm/client/config?tenantid=<tenant_id>";

Expected response: {"status":"success"}
```

**Verification Tasks (`customfield_17227`):**

```
Repeat the same steps in the pre-maintenance section to get inside the <namespace> pods, confirm the new flag value by running:

    curl -H 'Content-Type: application/json' "http://provisioner-pycore-provisioner-tm/client/config?tenantid=<tenant_id>" | jq -r '.data.<flag_name>';

Expected response: <new_value>
```

**Rollback Tasks (`customfield_17228`):**

```
Repeat the same steps in the pre-maintenance section to get inside the <namespace> pods, then run this command to turn the flag off to revert to the initial state:

    curl -X POST -H 'Content-Type: application/json' -d '{ "<flag_name>": "<old_value>"}' "http://provisioner-pycore-provisioner-tm/client/config?tenantid=<tenant_id>";

Expected response: {"status":"success"}
```

**Impact fields:**

| Field | Custom Field | Content |
|-------|-------------|---------|
| Expected Customer Experience | `customfield_17216` | `<description_text>` |
| Potential/Worst-case Customer Experience | `customfield_17217` | Feature flag did not take effect |
| Expected Internal Experience | `customfield_17133` | no |
| Potential/Worst-case Internal Experience | `customfield_17215` | no |
| Potential Side Effects | `customfield_17223` | no |
| Maintenance Impact | `customfield_27179` | Expected Impact: `<description_text>` / Potential Impact: Feature flag did not take effect |

**Fixed field defaults:**

| Field | Custom Field | Value (option ID) | Description |
|-------|-------------|-------------------|-------------|
| Urgency | `customfield_16290` | `39727` | Break Fix |
| Type of Change | `customfield_16792` | `{"id":"13191","child":{"id":"28422"}}` | Software > Feature Flag (cascading select) |
| Change Tier | `customfield_22582` | `25367` | Minor |
| Maintenance Event Title | `customfield_27025` | `"Data - Config Change in <DC>"` | Free text |
| Maintenance Event Type | `customfield_27026` | `37527` | Scheduled |
| Contained | `customfield_22102` | `24718` | Yes |
| Impacted Components | `customfield_18338` | `[{"id":"19536"}]` | Web UI |
| Escalated | `customfield_17021` | `13828` | No |
| Roadmap Item | `customfield_17763` | `16701` | NO |
| Customer Notification | `customfield_17218` | `14751` | No |
| Internal Notification | `customfield_17650` | `16382` | No |
| Additional Support | `customfield_17383` | `15259` | Not Needed |
| FedRAMP/PBMM | `customfield_20664` | `22746` | No |
| Opportunity Name | `customfield_11601` | `"Netskope"` | Free text |
| cm-needs-tech-review | `customfield_22581` | `25364` | true |
| cm-needs-bus-review | `customfield_22579` | `25361` | false |
| cm-needs-gov-review | `customfield_22580` | `25363` | false |
| SOC Escalation Level | `customfield_25939` | `31276` | L1 |
| Priority (custom) | `customfield_17843` | `16907` | 3 |

**Do NOT set** the `security` field — it is not on the create screen and causes a 400 error.

### Step 4: Present Draft for Confirmation

Show a preview:

```
CM Ticket Draft

Summary: Enable <flag_name> for tenant <tenant_id> (<tenant_url>) in <DC>
Type: Operational Change
Datacenter: <DC>
Namespace: <namespace>
Linked Issue: <eng_ticket>
Schedule: <begin> - <end>
Flag: <flag_name>
Tenant: <tenant_id> (<tenant_url>)
Change: <old_value> -> <new_value>

Expected Customer Experience: <description_text>

---
Confirm with "yes" / "create", or let me know what to change.
```

**Wait for user confirmation before creating.**

### Step 5: Create via Jira REST API

Read credentials from `~/.claude/mcp.json`:

```bash
ATLASSIAN_API_TOKEN=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_API_TOKEN' ~/.claude/mcp.json)
ATLASSIAN_USER_EMAIL=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_USER_EMAIL' ~/.claude/mcp.json)
ATLASSIAN_SITE_URL=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_SITE_URL' ~/.claude/mcp.json)
```

**Use `POST /rest/api/3/issue`** (NOT the deprecated `/rest/api/3/search`).

All rich-text fields (description, maintenance outline, pre/maintenance/verification/rollback tasks, impact fields) must use **ADF (Atlassian Document Format)**, not Markdown or Jira Wiki Markup.

After creating the ticket, link it to the ENG ticket:

```bash
curl -s -u "$EMAIL:$TOKEN" -X POST "$SITE/rest/api/3/issueLink" \
  -H "Content-Type: application/json" \
  -d '{"type":{"name":"Blocks"},"inwardIssue":{"key":"CM-XXXXX"},"outwardIssue":{"key":"ENG-XXXXXX"}}'
```

### Step 6: Confirm Creation

Output:

```
Created CM-XXXXX
  https://netskope.atlassian.net/browse/CM-XXXXX
Linked CM-XXXXX blocks ENG-XXXXXX
```

Note any items that need manual follow-up:
- Peer Review Approver (must be assigned manually or specify who)
- Schedule adjustment (if defaults were used)

## ADF Quick Reference

All rich-text custom fields in CM tickets require ADF format.

**Document wrapper:**
```json
{"type": "doc", "version": 1, "content": [...]}
```

**Paragraph:**
```json
{"type": "paragraph", "content": [{"type": "text", "text": "..."}]}
```

**Inline code:**
```json
{"type": "text", "text": "flag_name", "marks": [{"type": "code"}]}
```

**Heading:**
```json
{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "..."}]}
```

**Code block:**
```json
{"type": "codeBlock", "attrs": {"language": "bash"}, "content": [{"type": "text", "text": "..."}]}
```

**Bullet list:**
```json
{
  "type": "bulletList",
  "content": [
    {"type": "listItem", "content": [
      {"type": "paragraph", "content": [{"type": "text", "text": "item"}]}
    ]}
  ]
}
```

## Scheduling Defaults

If no schedule is provided, pick the next available maintenance window based on the datacenter's region (see `references/datacenters.md` for region classification):

| Region | Window (local time) | Timezone |
|--------|-------------------|----------|
| US | 8 PM - 2 AM | America/Los_Angeles |
| EU | 10 PM - 4 AM | Europe/Berlin |
| APAC | 10 PM - 4 AM | Australia/Sydney |
| MEA | 10 PM - 4 AM | Asia/Riyadh |

The schedule dates are stored in PDT (UTC-7) format in Jira:
- `customfield_16962` — Requested Begin Date
- `customfield_16963` — Requested End Date

Convert from the DC's local maintenance window to PDT before submitting.

## Error Handling

**400 with "security" error:** The `security` field is not on the create screen. Omit it.

**400 with "Specify a valid option" for Type of Change:** This is a cascading select. Use `{"id":"13191","child":{"id":"28422"}}` format, not `{"id":"28422"}`.

**Issue link fails:** The link type name is `"Blocks"` (case-sensitive). The CM ticket is the inward (blocking) issue.

## References

- `references/datacenters.md` — Datacenter codes, option IDs for both fields, region classification
