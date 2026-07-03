---
name: brain-first-hook
description: >-
  Enforce brain-first by a SessionStart hook, not memory. Wire a templated hook (startup|resume|clear)
  that injects "the OBrain is source of truth; FIRST action is read the vault" into every session start —
  so orienting from the brain is harness-guaranteed, not the agent's discretion. Use when a node keeps
  drifting to its own context after /clear. Pairs with brain-sync, vault-lookup.
---

# brain-first-hook  ·  applies-when: any node with an OBrain

`brain-first` is a Core rule, but as a *convention the agent must remember* it fails exactly where it matters
— after a `/clear`/resume the agent orients from its own context instead of the vault. Fix: make it
**harness-enforced.**

## The hook
A **SessionStart hook** (matchers `startup|resume|clear`) in the node's settings that, on every session
start/clear, injects a directive:
> *The OBrain is the source of truth and SUPERSEDES your own context/reasoning/API. FIRST action before
> answering anything about prior state: run `vault-lookup` → read the latest Handoff + Open Actions + log tail.*

- The directive **text lives in a small file** the hook prints, so wording is editable without touching settings.
- **Parameterize per node:** the vault path + entry-point notes (which index/handoff to read first).
- **Layer-D-free:** the hook only points at the node's *own* OBrain; it carries no secrets.

## Why it works
Memory is advisory — the agent can pattern-match the literal question and skip the vault. A hook fires
unconditionally, so "orient from the brain first" is structural, not optional.

Up: [capabilities.md](../../capabilities.md)
