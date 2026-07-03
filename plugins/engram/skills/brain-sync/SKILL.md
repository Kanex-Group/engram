---
name: brain-sync
description: >
  Session-start sync ritual for Engram. Use at the START of a session in any
  project that consumes the engram plugin, or when the human says "brain sync", "sync check",
  "sync the brain", or asks to adopt/pull brain improvements. Pulls Core, proposes capability
  adoptions (auto-adopt safe ones, ASK on massive/uncertain ones), and promotes good local
  inventions back up to Core. Never copies project secrets (Layer D).
---

# brain-sync

Engram has four layers: **A** capabilities (skills), **B** methods/habits, **C** the
**human layer** (personal truth — about whichever human drives the brain), and **D** project
secrets. **A/B/C live in Core and travel. D never leaves its home project.**

## When to run
- At the **start of a session** in any project that uses `engram`.
- When the human says *"brain sync" / "sync check" / "sync the brain"*.

## Auto-trigger & off-switch (truly-auto ↔ semi-auto)
Each connected project carries a **`Brain Sync.md`** note in its vault with an **`auto_sync`** frontmatter
flag, and its `CLAUDE.md` wires the trigger:
- **`auto_sync: true`** → **truly auto**: run this skill automatically at session start (auto-adopt safe
  changes, ASK on big/uncertain ones).
- **`auto_sync: false`** → **semi-auto**: run only when the human says "brain sync".

The human toggles by flipping `auto_sync` in that project's `Brain Sync.md` — no code change. New projects:
add the `auto_sync` flag to their `Brain Sync.md` and the trigger block to their `CLAUDE.md` (see an
existing project for the exact wording).

## Announce, then run (big-sync confirm)
At session start, first quick-check whether a sync is even needed:
- **Needed + small** → **announce** ("running a brain sync"), then run it (auto-adopt safe, ASK on big).
- **Needed but big** (would interrupt the human's workflow) → **ask first**: "big sync awaiting — do it now,
  or function as-is and sync later?" — and respect the answer.
- **Not needed** → say nothing; proceed.

## The ritual
1. **Locate Core** (the `engram` plugin root) and the project's `last_sync` marker
   (`.brain/last_sync` in the project, or session 0 if absent).
2. **Read `capabilities.md`** in Core + its `CHANGELOG.md` since `last_sync`.
3. **Match** each new — *and each previously-skipped* — capability against the project's profile
   using its **`applies-when`** tag (re-check skipped ones: a capability that didn't fit before may
   fit now, e.g. money-path-guard once a project adds payments).
4. **Risk-tier gate** (Decision 2):
   - **Auto-adopt silently** when the change is **additive + low-risk** (new template, new doc,
     bug-fix to a skill, brand-new standalone skill).
   - **ASK the human first** when it is **massive/structural**, touches **money / security /
     anti-cheat** paths, or would **overwrite a file the project has customized** (Decision 5:
     flag-and-ask — show both versions, let the human confirm or merge).
5. **Adopt** approved/auto items into the project; **bump `last_sync`**.
6. **Reverse-promote (capabilities, conventions, AND learn-tickets):** scan the node for anything generic
   not yet in Core and file it UP via the `PROPOSE` inbox (Layer-D stripped):
   - **capabilities** — a locally-invented skill → promote it;
   - **convention memories** — generic Layer-B method / Layer-C human-truth (e.g. how to work with the
     founder) → propose into Core's human/method layer;
   - **learn-tickets** — sweep the node's proposed learn-tickets and surface each as a
     proposal, so node learn-tickets reach Core for triage instead of rotting node-local.
7. **Surface, don't silo:** report any Core `Dev-Core Proposals` entries still `status: open` (plus any
   learn-tickets swept this run) so parked items are visible, not invisible (pairs with `tools/digest.py`).

## Hard rules
- **Never** copy Layer-D project secrets into Core or between projects.
- Nothing risky auto-applies — the human confirms (Decision 2 + 5).
- Keep `capabilities.md` + `CHANGELOG.md` the source of truth for "did the brain improve?".

## Output
A short adoption table: `capability | what changed | applies because… | auto / ASK | result`,
followed by any reverse-promotion proposals.
