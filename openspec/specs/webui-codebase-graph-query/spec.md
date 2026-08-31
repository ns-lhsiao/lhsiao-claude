### Requirement: Global invocability
The `/graphify-webui` skill and its two domain agents (`webui-angular-agent`,
`webui-php-agent`) SHALL be defined in `~/.claude/` (global scope) and SHALL resolve
and dispatch correctly from a session whose working directory is any repo, not only
the `webui` checkout.

#### Scenario: Invoked from a different repo
- **WHEN** a session with cwd outside `webui` (e.g. investigating a bug in another
  repo whose fix touches `src/webui/...`) invokes `/graphify-webui "<question>"`
- **THEN** the skill resolves, dispatches both domain agents, and returns a
  synthesized answer, exactly as if invoked from inside the `webui` checkout

#### Scenario: Invoked from inside the webui checkout
- **WHEN** a session with cwd inside the `webui` repo invokes `/graphify-webui`
- **THEN** the skill still resolves and behaves identically (global scope is a
  superset of the prior project-scoped behavior, not a narrower one)

### Requirement: Unconditional parallel dispatch
The `/graphify-webui` skill SHALL dispatch both `webui-angular-agent` and
`webui-php-agent` in parallel on every invocation, with no domain classifier
deciding to skip either one.

#### Scenario: Single-domain question
- **WHEN** the user asks a question that is unambiguously about only one domain
  (e.g. a specific PHP controller method)
- **THEN** both agents are still dispatched; the irrelevant domain's agent returns
  an early "not relevant" result that the skill drops from the synthesized answer

### Requirement: Absolute graph path pinning
Each domain agent SHALL query its `graphify` knowledge graph using a pinned
absolute `--graph <path>` on every invocation, never a path relative to its own
cwd.

#### Scenario: Agent invoked from an arbitrary cwd
- **WHEN** `webui-angular-agent` or `webui-php-agent` runs any `graphify` subcommand
- **THEN** the command includes the agent's pinned absolute graph path regardless
  of what the caller session's or the agent's own cwd happens to be

### Requirement: Build-if-missing fallback
Each domain agent SHALL check whether its `graph.json` exists before querying, and
SHALL run a full `graphify` build if it is missing, before proceeding.

#### Scenario: Graph file absent or deleted
- **WHEN** a domain agent's pinned `graph.json` does not exist (first-ever run, or
  deleted/corrupted between scheduled maintenance runs)
- **THEN** the agent runs a full build from its worktree root before answering,
  rather than failing or answering without graph grounding

### Requirement: Early return on low first-pass relevance
Each domain agent SHALL run one cheap, narrow-budget first-pass `graphify query`
before any deeper `path`/`explain`/`affected` follow-up, and SHALL stop and report
"not relevant to this domain" if that first pass finds nothing relevant — judged as
an empty result or a result that is clearly unrelated boilerplate, not a raw
node-count threshold.

#### Scenario: First pass finds nothing relevant
- **WHEN** a domain agent's first-pass query returns no relevant nodes/edges
- **THEN** the agent stops immediately and reports the domain is not relevant,
  without running further `path`/`explain`/`affected` queries

### Requirement: Answer synthesis with attribution
The `/graphify-webui` skill SHALL drop any domain agent's "not relevant" result
from the synthesized answer, and SHALL present both domains' answers as separately
attributed sections (never merged into a single unified claim) when both report
relevant material.

#### Scenario: Only one domain has relevant material
- **WHEN** exactly one domain agent returns a relevant answer and the other returns
  "not relevant"
- **THEN** the synthesized response presents only the relevant domain's answer,
  without noting that the other domain was checked and found nothing (unless the
  question genuinely implied both domains should have something)

#### Scenario: Both domains have relevant, non-overlapping material
- **WHEN** both domain agents return relevant answers
- **THEN** the synthesized response presents them as clearly-attributed separate
  sections and does not imply a cross-domain connection that neither graph asserts

### Requirement: Failure surfacing, not fabrication
A domain agent SHALL surface a `graphify` command failure (missing binary, corrupt
graph, non-zero exit) plainly in its answer, and SHALL NOT fall back to guessing an
answer from general knowledge to fill the gap.

#### Scenario: graphify command fails
- **WHEN** a domain agent's `graphify` invocation fails for any reason
- **THEN** the agent reports the failure explicitly in its response rather than
  producing an unattributed or fabricated answer
