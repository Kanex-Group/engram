---
name: wiki-sync
description: >-
  Keep a project's OBrain codebase Wiki in sync with the code (the Ingest op of the LLM-Wiki pattern).
  Use after changing app code — models, views, consumers/handlers, settings, or commands — to update
  the matching Wiki page in the SAME session so docs never drift.
---

# wiki-sync  ·  applies-when: project mirrors code into a derived Wiki

The Wiki is a snapshot of the code; its #1 risk is going stale. Doc-sync rule: **touch app code → update
its docs in the same session.** This skill **is** the `Ingest(code)` operation of the LLM-Wiki pattern
(after Karpathy's "LLM Wiki"): the `Wiki/` store is a *derived projection* of the code.

## Scope (hard)
Writes to `Wiki/` **only** — never to authored stores (`Decisions/`, `Confidential/`, `Compliance/`,
`Knowledge/`, `Main Defi/` or their per-project equivalents). Those are primary human knowledge; the Wiki
is the one store where code is the source of truth.

## What to update by change type (generic)
| You changed… | Update |
| --- | --- |
| a model / migration | the Data Model page + the app's Wiki page (+ schema/DBA note if constraints/indexes) |
| a handler / route / socket message | the protocol/endpoints page + the app's Wiki page |
| a view / URL / endpoint | the app's Wiki page |
| settings / env var / flag | the Settings & Configuration page |
| a command / process entry | the Commands/Runbooks page |
| money / ledger / payout | the Payments/Ledger Wiki page (link to the authored money note, don't duplicate) |
| confidential heuristics | the project's **Confidential** store only — NOT git, NOT the Wiki |

## Rules
- Keep the Wiki at the "what/where"; the "why" stays in authored concept notes — **link, don't duplicate**.
- New recurring bug class → also touch the Repeat-Offenders note.
- Re-run the link-integrity check (no orphans) after edits (`vault-lint`).
- **Log it (Ingest):** append one line to the vault's `log.md` → `## [YYYY-MM-DD] ingest | <app> → <pages>`.
