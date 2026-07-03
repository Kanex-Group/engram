---
name: obrain-schema
description: >-
  The canonical OBrain vault schema — the folder structure, indexes, conventions, and graph colors a
  project's Obsidian knowledge base should follow. Use when scaffolding a new project's OBrain, or
  auditing an existing one for missing stores. Pairs with vault-lookup,
  new-dev-note, wiki-sync, vault-lint.
---

# obrain-schema  ·  applies-when: any project wanting a knowledge base

The canonical shape of an OBrain vault (lives **outside** the repo, gitignored). Scaffold a new project to
this; audit an existing one against it (a project may, e.g., be missing `Wiki/` + `Raw/`).

## Stores
| Store | Holds | Source of truth? |
|---|---|---|
| `Home.md` | master map / entry point | — |
| `Main Defi/` | product overview, architecture, concept notes | **authored (human)** |
| `Dev_Sessions/` | the spine: `Sessions/` → `Issues/` → `Fixes/` → `Session Handoff/`, plus `Open Actions.md`, `Optimization Log.md`, `Prod QA & Merge Gate.md`, `QA_TEMPLATE.md`, append-only `log.md` | authored |
| `Wiki/` | **derived** projection of the code (Ingest via `wiki-sync`) | **code** |
| `Raw/` | manifest mapping source files → Wiki pages (pointers only, no code copied) | — |
| `Knowledge/` | playbooks (concurrency, environment parity, repeat offenders) | authored |
| `Decisions/` | ADRs | authored |
| `Confidential/` | secret/Layer-D material (thresholds, IP) — **never in git** | authored |
| `Compliance/` | regulatory (if applicable) | authored |
| `Learn/` | `User_Learn_Prompts/LP_#` + `Claude_Notes/` (see `learn-mode`) | authored |
| `C-Suite/` + `Human-Gate/` | **optional company layer** — scoped propose-only function-node dirs (each with its brain + `Reports/`) under an AI-CEO, plus the human front desk; see `company-layer` | authored / propose-only |

## Conventions
- **Index-first read policy** — open the index/table note, follow only linked notes; never full-scan.
- **Next-free-IDs marker** atop the sessions index; bump it, don't scan the table.
- **IDs:** one prefixed scheme per store (e.g. session / issue / fix / feature), `####` numbered; `0000` = template, real work `0001`+.
- **Status tags:** `#idea → #spec → #building → #review → #done`.
- `[[wikilink]]` everything **inside the vault**; nothing orphaned. **Private Claude memory lives *outside*
  the vault** — reference a memory as plain text `memory:slug`, **never** a `[[wikilink]]` (it dangles in
  Obsidian).
- **Memory vs vault boundary** — the **vault** holds project/code knowledge (decisions, issues,
  fixes, sessions, Wiki, playbooks) and is the shared source of truth; **private memory** holds cross-session
  operating facts about working with the human (conventions, preferences, pointers) and stays small. **One
  fact, one home** — don't duplicate; if it's in the vault, memory just points to it. Generic conventions
  promote to Core's human layer; Layer-D secrets stay in `Confidential/` only.
- **Graph colors:** one distinct color group per store (Obsidian `.obsidian/graph.json`), no repeats.
- **Scope guard:** Ingest/Lint write to `Wiki/` only; authored stores are flagged, never auto-rewritten.

> Only build the stores a project actually needs yet (velocity > ceremony) — but keep the names/conventions
> identical across projects so the brain's skills work everywhere.
