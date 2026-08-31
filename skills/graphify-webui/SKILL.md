---
name: graphify-webui
description: >
  Use this skill for any question about webui's architecture, code relationships,
  or "how does X work" / "what calls Y" / "how are A and B related" questions about
  the webui codebase (Angular frontend or PHP backend). Runs inline in the caller's
  own session — dispatches to webui-angular-agent and webui-php-agent in parallel,
  each querying its own persistent graphify knowledge graph, and synthesizes their
  answers. Trigger phrases: "/graphify-webui", "how does X work in webui", "trace
  the path from X to Y", "what breaks if I change X", or any orientation question
  about webui source before manual Read/Grep.
---

# /graphify-webui

Graph-informed first pass on webui source, before falling back to manual Read/Grep/Explore.

## What this skill does

Dispatches the question to **both** domain agents in parallel, unconditionally — there is no domain classifier deciding which one to skip (a classifier's wrong guess would silently drop the correct domain's answer with no safety net; see design.md Decision 4 in `openspec/changes/webui-graphify-agents/`). Each domain agent runs its own cheap first-pass check and early-returns "not relevant" if its graph has nothing — that's where the actual cost savings come from (see Decision 10), not from skipping dispatch.

## Step 1 — Dispatch both agents in parallel

Always launch both in the same message (parallel `Agent()` calls), passing the user's question through with minimal rewriting:

```
Agent({ subagent_type: "webui-angular-agent", description: "Query Angular graph", prompt: "<question>" })
Agent({ subagent_type: "webui-php-agent",     description: "Query PHP graph",     prompt: "<question>" })
```

Do this even if the question looks unambiguously single-domain — the irrelevant agent's early-return costs one cheap first-pass query, not a full dig, and it removes the risk of a wrong guess about which domain the question "obviously" belongs to.

## Step 2 — Synthesize

Once both return:

- If an agent's answer is a "not relevant to this domain" early-return, **drop it entirely** from the synthesized response — don't mention that domain was checked and found nothing, unless the user's question genuinely implied both domains should have something (in which case note the absence briefly, e.g. "no PHP-side involvement found for this").
- If both agents found relevant material, present both as clearly-attributed sections (e.g. "**Angular side:** ... / **PHP side:** ...") rather than merging them into one claim — the two graphs are independent extractions with no verified cross-language edges between them (federated design, see design.md). Do not imply a connection between the two answers that neither graph actually asserts.
- If both agents report a failure (graphify errored, graph missing and rebuild failed, etc.), surface that plainly — don't paper over it with a guessed answer.

## Step 3 — Hand off

After presenting the graph-informed answer, proceed with normal Read/Grep/Explore as needed to verify or go deeper — this skill is a first pass, not a replacement for direct source inspection. This is a soft gate, not a hard one: if the skill itself is unavailable or a domain agent isn't found (e.g. registry not yet reloaded after the agent files were added), fall through to normal exploration rather than blocking.
