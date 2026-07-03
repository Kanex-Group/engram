---
name: vault-lookup
description: >-
  Look things up in and operate a project's OBrain vault (Obsidian knowledge base). Use at the
  start of any work session, before answering questions about the codebase/architecture/decisions,
  and to open/close sessions and log Issues/Fixes/Handoffs. Enforces the balanced read policy
  (open index → follow one linked note), the Session→Issues→Fixes→Handoff loop, the Next-free-IDs
  marker, and closing only on Session_END. Applies to any project with an OBrain.
---

# vault-lookup  ·  applies-when: project has an OBrain/Obsidian vault

OBrain is a project's knowledge vault and **source of truth** (code never overrides it). Each project's
vault lives **outside** its git repo and its location is recorded in the project's `CLAUDE.md` / `Home.md`.
This skill is how you read it and run the dev loop.

## Balanced read policy (always)
1. Open the relevant **index/table note first** — never full-scan the vault. The tables are the map.
   Typical entry points (names vary per project): `Home.md` / overview note · the master sessions log
   (`Sessions Main.md`) · indexes for Issues / Fixes / Handoffs / Open Actions · the derived codebase
   `Wiki/` · the activity `log.md` (read its last lines on session start for recent context).
2. From the index, follow **only the directly-linked** note(s) you actually need.
3. "OBrain" and any clear typo (≥85% confidence) mean this vault.

## Start a session (human triggers work)
A session is **human-bounded**: one note, appended to across many prompts. Do **not** open a new session
per message. To open:
1. **Branch first:** `git checkout -b sxn-####-short-desc` (never work on `main`).
2. Read the top **Next-free-IDs marker** in the sessions index; use the Sxn number and **bump the marker**
   (don't scan the table).
3. Create the session note from the project's `0000` template (with a `branch:` frontmatter field); add a
   row to the sessions index.

## During the session
- Log a problem → an Issue note (bump the IS marker); add to the Issue index.
- Log a resolution → a Fix note (bump the Fx marker), linked to its Issue; add to the Fix index.
- `[[wikilink]]` everything; nothing orphaned.
- **Branch-hop safely when editing repo docs.** When a session touches always-loaded repo files
  (`CLAUDE.md`, skill files, configs) and spans multiple branches, **batch all edits to a file on
  its branch before switching away** (or stage that file's change last), and **re-read the file
  after any branch switch**. Branch-hopping mid-edit desyncs the editor's file-state tracking and
  triggers "file modified since read" retries.

## Close a session — ONLY on `Session_END`
Close **only** when the human says `Session_END` (or a clear ≥85%-confidence equivalent). Then write the
Handoff note (done / outstanding / refs + one concrete workflow-improvement line), index it, update Open
Actions, and mark the session `done`.

## Guardrails (Layer C — apply to every project)
- **Never push `main`** without the project's exact approval phrase (its merge gate; see `pre-merge-check`).
- Never commit the vault, `.obsidian/`, DBs, secrets, or financials.
- Keep any confidential/Layer-D material (thresholds, secret heuristics) in the project's confidential
  store only — never in git, never in Core.
- Flag the human on conflicted decisions (e.g. vendor/client COI).
