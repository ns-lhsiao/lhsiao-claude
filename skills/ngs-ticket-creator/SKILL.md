---
name: ngs-ticket-creator
description: Create NGS (Government Services) Jira tickets for operational tasks on government stacks (FedRAMP, PBMM, pre-prod). Use when users need to file NGS tasks for WebUI migrations, validations, break-fixes, or deployments targeting government environments. Triggers on "create NGS ticket", "file NGS task", or any request to track operational work against a fedramp/pbmm/pre-prod stack.
---

# NGS Ticket Creator

Create operational Task tickets in the NGS (Government Services) Jira project for work targeting government stacks (FedRAMP, PBMM, pre-prod environments).

## When to Use This Skill

Use this skill when users request to:
- Create an NGS ticket for a migration, validation, or fix on a government stack
- File an operational task for the NGS team (fedramp, pbmm, pre-prod)
- Track government-environment execution of a change derived from an ENG ticket
- Create break-fix, deployment, or information-gathering tasks in NGS

## Project Metadata

**Project:** NGS (project key: `NGS`, project ID: `16767`)

**Issue Type — always Task** (id: `3`) unless user specifies otherwise.

**Components** — infer from context, ask if ambiguous:

| Component | ID | Use When |
|---|---|---|
| `break-fix` | 36110 | Migrations, schema fixes, data repairs, bug validation |
| `deployments` | 35248 | Deploying a build or release to government stack |
| `information-gather` | 36322 | Collecting logs, HAR files, data for investigation |
| `internal development` | 36657 | Engineering work internal to the NGS team |
| `documentation` | 37188 | Writing or updating runbooks/docs |
| `support` | 38256 | Customer-facing support tasks |
| `hardware` | 35947 | Physical hardware provisioning/repair |
| `gslb` | 41386 | GSLB/traffic routing changes |
| `pdv` | 37826 | PDV-related tasks |
| `toss` | 40818 | TOSS team tasks |
| `training` | 37694 | Training activities |
| `team-goals` | 39019 | Team OKR/goal tracking |

**Default priority:** Major (id: `3`)

## Workflow

### Step 1: Gather Context from User

Extract the following from the user's request:

- **Target stack(s)** — e.g., FedRAMP, PBMM, FedRAMP Pre-Prod, FedRAMP Prod. If multiple stacks, create one ticket per stack.
- **Reference ENG/CM ticket** — the upstream ticket driving this work (e.g., ENG-949029).
- **Task type** — what needs to be done: migration, validation, break-fix, deployment, etc.
- **Steps** — any specific runbook steps the user provides. Include verbatim.

If the user has not provided steps but references an ENG ticket, fetch the `Fix QA Test Recommendations` field (`customfield_12503`) from that ticket to use as the step source.

### Step 2: Infer Component

Apply this logic:
- Migration / schema change / index validation → `break-fix`
- Deploying a version → `deployments`
- Collecting data / logs / files for investigation → `information-gather`
- Internal NGS engineering work → `internal development`
- When unclear → ask the user

### Step 3: Draft Ticket(s)

**Summary format:** `[Action] on [component/table] - [Stack Label]`

Examples:
- `Assist on running userkey index migration on client_support_requests - FedRAMP/PBMM`
- `Validate userkey indexes on client_support_requests - FedRAMP Pre-Prod`

**Description** — use ADF (Atlassian Document Format). Structure:

```
[1-2 sentence context paragraph linking to the ENG/CM reference ticket]

Reference: https://netskope.atlassian.net/browse/ENG-XXXXXX

Steps:
1. [step one]
   [code block if applicable]
2. [step two]
   ...
```

For steps involving shelling into a webui pod, always include:

```
Log in to a webui pod. Use kubectl to access any running webui pod.
The specific pod name will vary.

kubectl exec -ti -n [namespace] webui-webui-xxxxx-xxxx -- bash
# Example
# kubectl exec -n lon3-mp-prod--webui webui-webui-77f774b744-84ggs bash
```

### Step 4: Present Draft for Confirmation

Show the user:

```
📋 NGS Ticket Draft — [Stack Label]

Summary: [summary]
Type: Task
Component: [component name]
Priority: Major
Reference: [ENG/CM key]

Description:
[formatted description preview]

---
Confirm with "yes" / "create", or let me know what to change.
```

If creating multiple tickets (e.g., one per stack), show all drafts together before creating any.

**Wait for user confirmation before creating.**

### Step 5: Create via Jira REST API

Read credentials from `~/.claude/mcp.json`:

```bash
ATLASSIAN_API_TOKEN=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_API_TOKEN' ~/.claude/mcp.json)
ATLASSIAN_USER_EMAIL=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_USER_EMAIL' ~/.claude/mcp.json)
ATLASSIAN_SITE_URL=$(jq -r '.mcpServers.atlassian.env.ATLASSIAN_SITE_URL' ~/.claude/mcp.json)
```

Create the ticket:

```bash
curl -s -u "$ATLASSIAN_USER_EMAIL:$ATLASSIAN_API_TOKEN" \
  -X POST "$ATLASSIAN_SITE_URL/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "NGS"},
      "issuetype": {"id": "3"},
      "summary": "SUMMARY_HERE",
      "priority": {"id": "3"},
      "components": [{"id": "COMPONENT_ID"}],
      "description": { ...ADF... }
    }
  }' | jq '{key: .key, self: .self}'
```

When creating multiple tickets, run them sequentially and collect all keys before confirming.

### Step 6: Confirm Creation

Output for each created ticket:

```
✅ NGS-XXXX created — [Stack Label]
   https://netskope.atlassian.net/browse/NGS-XXXX
```

## ADF Quick Reference

Paragraph:
```json
{"type": "paragraph", "content": [{"type": "text", "text": "..."}]}
```

Inline code:
```json
{"type": "text", "text": "my_table", "marks": [{"type": "code"}]}
```

Bold:
```json
{"type": "text", "text": "FedRAMP / PBMM", "marks": [{"type": "strong"}]}
```

Link:
```json
{"type": "text", "text": "ENG-949029", "marks": [{"type": "link", "attrs": {"href": "https://netskope.atlassian.net/browse/ENG-949029"}}]}
```

Ordered list item:
```json
{
  "type": "orderedList", "attrs": {"order": 1},
  "content": [
    {"type": "listItem", "content": [{"type": "paragraph", "content": [...]}]}
  ]
}
```

Code block:
```json
{"type": "codeBlock", "content": [{"type": "text", "text": "..."}]}
```

## Updating Existing Tickets

To update description or other fields on an existing NGS ticket, use PUT:

```bash
curl -s -u "$ATLASSIAN_USER_EMAIL:$ATLASSIAN_API_TOKEN" \
  -X PUT "$ATLASSIAN_SITE_URL/rest/api/3/issue/NGS-XXXX" \
  -H "Content-Type: application/json" \
  -d '{"fields": {"description": { ...ADF... }}}'
```

A 204 (empty body) response means success. Use `&& echo "updated"` to confirm.

## Multi-Stack Pattern

When the same task needs to run on multiple stacks (e.g., FedRAMP/PBMM and FedRAMP Pre-Prod), create one ticket per stack:
- Same description structure, only the stack label in the summary and intro paragraph differs
- Show all drafts together before creating any
- Report all keys together after creation

## Error Handling

**curl returns error JSON:** Parse `.errors` or `.errorMessages` from the response to identify the problem (missing required field, bad component ID, etc.).

**Component not found:** Recheck component ID against the table above. NGS components are different from ENG/other projects.

**Description rendering issues:** Validate ADF structure — every `content` array must contain valid node objects. Never mix plain string and ADF.

## Example

**User:** "Create NGS tickets for ENG-949029 targeting FedRAMP/PBMM and FedRAMP Pre-Prod"

**Flow:**
1. Fetch ENG-949029 → Task: "Assist on adding userkey index migration", QA steps available
2. Infer component: migration/validation → `break-fix`
3. Draft two tickets — one per stack — with kubectl exec steps + SHOW CREATE TABLE validation
4. Present both drafts, wait for confirmation
5. Create NGS-5719 (FedRAMP/PBMM) and NGS-5720 (FedRAMP Pre-Prod)
6. Report both keys with links
