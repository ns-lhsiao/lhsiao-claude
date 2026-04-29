---
name: ui-client-hygiene-review
description: Diagnose why a Jira ticket was caught by the UI-Client Jira hygiene rule. Fetches ticket metadata and development info from Jira, then evaluates which clause of the hygiene rule matched. Triggers on "why was this ticket caught", "hygiene review", "jira hygiene check", or any request to explain why a ticket appears in the hygiene filter.
---

# UI-Client Jira Hygiene Review

Diagnose why a Jira ticket was flagged by the UI-Client Jira hygiene rule and
recommend the fix to clear it.

## Prerequisites

Jira credentials are read from `~/.claude/mcp.json` under
`mcpServers.atlassian.env`:

- `ATLASSIAN_API_TOKEN`
- `ATLASSIAN_USER_EMAIL`
- `ATLASSIAN_SITE_URL`

Use `curl -s -u "$EMAIL:$TOKEN"` for all Jira REST calls.

## The Hygiene Rule

The rule is a disjunction of five top-level clauses, all gated by
`resolutionDate >= 2022-11-01`. A ticket appears in the filter when **any one
clause** matches.

### Clause 1 — Resolved non-Fixed with linked PRs

```
resolution != Fixed
AND development[pullrequests].all > 0
AND issuetype in (Bug, Story, Task)
AND labels not in (jira-reverted, PR-declined)
```

**Why it fires:** A ticket has PRs linked but was not resolved as Fixed. This
suggests either the resolution is wrong (should be Fixed) or the PRs should be
declined/reverted and labelled accordingly.

**How to clear:** Change resolution to Fixed, or add label `jira-reverted` or
`PR-declined` as appropriate.

### Clause 2 — Bug fixed without code

```
issuetype = Bug
AND resolution = Fixed
AND development[pullrequests].all = 0
AND development[commits].all = 0
AND labels not in (content_fix)
AND summary !~ XRAY
AND summary !~ coverity scan
```

**Why it fires:** A bug was marked Fixed but has no linked PRs or commits. The
fix either happened outside version control or the developer forgot to include
the ticket key in the branch/commit.

**How to clear:** Link the PR/commits to the ticket (branch or commit message
must contain the ticket key), or add label `content_fix` if no code change was
needed.

### Clause 3 — Duplicate without hygiene filter match

```
resolution = Duplicate
AND filter != kartik-jira-hygiene-duplicate-issues
AND summary !~ XRAY
AND summary !~ coverity scan
```

**Why it fires:** The ticket is resolved as Duplicate but is not in the
curated duplicate-issues filter.

**How to clear:** Ensure the ticket is linked to its duplicate and appears in
the `kartik-jira-hygiene-duplicate-issues` filter, or change the resolution if
Duplicate is incorrect.

### Clause 4 — Blocker bug missing RCA fields

```
priority = Blocker
AND issuetype = Bug
AND resolution = Fixed
AND (
    Root Cause Analysis is EMPTY
    OR Fix Description is EMPTY
    OR Fix QA Test Recommendations is EMPTY
)
AND summary !~ XRAY
AND summary !~ coverity scan
```

**Why it fires:** A Blocker-priority bug was fixed without filling in all
three post-mortem fields.

**How to clear:** Populate **Root Cause Analysis**, **Fix Description**, and
**Fix QA Test Recommendations** on the ticket.

### Clause 5 — Escalated bug / closed epic missing release metadata

This clause is itself a disjunction of seven sub-clauses. They share a common
base (`filter = generic-base-filter`).

#### 5a-5c — Escalated bug missing dropdowns

Matches when ALL of:

```
type = Bug
labels = jira_escalated
status in (Closed, "Pending Close")
resolution = Fixed
```

AND **any one** of these dropdown fields is empty:

| Sub-clause | Empty field |
|------------|-------------|
| 5a | Release Note\[Dropdown\] |
| 5b | Documentation Required\[Dropdown\] |
| 5c | TOI Required\[Dropdown\] |

**How to clear:** Fill in all three dropdown fields on the ticket.

#### 5d-5f — Closed epic missing release metadata

Matches when ALL of:

```
type = Epic
status = Closed
resolution = Done
summary !~ Xray / sonarcube / deployment / nonprod
parent is EMPTY
labels not in (ess_survey_tool, no-code, no_code) OR labels is EMPTY
filter = "Jira Extended Search - Epics with no Linked NPLAN"
```

AND **any one** of these dropdown fields is empty:

| Sub-clause | Empty field |
|------------|-------------|
| 5d | Release Note\[Dropdown\] |
| 5e | Documentation Required\[Dropdown\] |
| 5f | TOI Required\[Dropdown\] |

**How to clear:** Fill in all three dropdown fields on the epic, or link an
NPLAN issue to it.

## Workflow

### Step 1: Fetch ticket metadata

```bash
curl -s -u "$EMAIL:$TOKEN" \
  "$SITE/rest/api/3/issue/$KEY?fields=summary,issuetype,resolution,status,priority,labels,resolutiondate,parent" \
  | jq '{summary: .fields.summary, issuetype: .fields.issuetype.name,
         resolution: .fields.resolution.name, status: .fields.status.name,
         priority: .fields.priority.name, labels: .fields.labels,
         resolutiondate: .fields.resolutiondate, parent: .fields.parent}'
```

### Step 2: Fetch development info (PRs and commits)

Get the issue's internal ID first, then query the dev-status API:

```bash
ISSUE_ID=$(curl -s -u "$EMAIL:$TOKEN" "$SITE/rest/api/3/issue/$KEY?fields=id" | jq -r '.id')

# PR count
curl -s -u "$EMAIL:$TOKEN" \
  "$SITE/rest/dev-status/latest/issue/detail?issueId=$ISSUE_ID&applicationType=GitHub&dataType=pullrequest" \
  | jq '{pr_count: (.detail[].pullRequests | length),
         prs: [.detail[].pullRequests[]? | {title: .name, status: .status}]}'

# Commit count
curl -s -u "$EMAIL:$TOKEN" \
  "$SITE/rest/dev-status/latest/issue/detail?issueId=$ISSUE_ID&applicationType=GitHub&dataType=repository" \
  | jq '.detail[].commits | length'
```

### Step 3: Fetch release metadata fields (if Clause 4 or 5 is plausible)

The relevant custom field IDs (may vary — discover via `/rest/api/3/field`
filtered by name if these return null):

| Field name | Known IDs to try |
|------------|-----------------|
| Release Note\[Dropdown\] | `customfield_24133`, `customfield_17597`, `customfield_16820` |
| Documentation Required\[Dropdown\] | `customfield_24136`, `customfield_17599`, `customfield_17078` |
| TOI Required\[Dropdown\] | `customfield_16173` |
| Root Cause Analysis | discover via field search |
| Fix Description | discover via field search |
| Fix QA Test Recommendations | discover via field search |

Fetch them:

```bash
curl -s -u "$EMAIL:$TOKEN" \
  "$SITE/rest/api/3/issue/$KEY?fields=customfield_24133,customfield_24136,customfield_16173,customfield_17597,customfield_17599,customfield_16820,customfield_17078" \
  | jq '.fields'
```

If all return null, fall back to discovering field IDs:

```bash
curl -s -u "$EMAIL:$TOKEN" "$SITE/rest/api/3/field" \
  | jq '[.[] | select(.name | test("Release Note|Documentation Required|TOI Required"; "i"))] | .[] | {id: .id, name: .name}'
```

### Step 4: Evaluate each clause

Walk through clauses 1-5 in order. For each clause, check every condition
against the fetched data. Present the evaluation as a table showing each
condition, the ticket's actual value, and whether it matches.

Stop at the **first fully matching clause** — that is the reason the ticket was
caught. If multiple clauses match, report all of them.

### Step 5: Recommend the fix

Based on the matching clause, state exactly which field(s) need to be updated
or which label(s) need to be added to clear the ticket from the hygiene filter.

## Output Format

1. **Ticket summary** — one-line recap of the ticket.
2. **Matching clause** — clause number and name.
3. **Evaluation table** — condition / actual value / match for the matching clause.
4. **Recommendation** — concrete action to clear the ticket.

Keep it concise. No preamble, no caveats.
