---
name: new-dev-note
description: >-
  Scaffold a new OBrain dev-log note (Session / Issue / Fix / Feature / Handoff) with the correct
  next ID, frontmatter, folder, index-table row, and nav/up footer — and bump the Next-free-IDs
  marker. Use whenever opening a session, logging an issue or a fix, or writing a handoff in any
  project's OBrain. Pairs with vault-lookup.
---

# new-dev-note  ·  applies-when: project uses the Dev_Sessions spine

Creates a dev-spine note consistently so IDs, indexes, and the marker never drift. Vault location +
exact templates are per-project (see the project's `CLAUDE.md`).

## Always, first
Open the sessions index, read the top marker
`> Next free IDs — Sxn: #### · IS: #### · Fx: #### · FT: ####`. Use the number for the type you're
creating and **bump that field** (don't scan the table).

## Note types (copy the project's `0000` template for each)
- **Session** (`ID_<Session>_####`): frontmatter `id, type: session, status: open, branch, date`; branch-first
  before creating; add a row to the sessions index; nav footer to the index + prev/next + boards.
- **Issue** (`ID_<Issue>_####`): frontmatter `id, type: issue, severity, area, status, session, date`; add a row
  to the Issue index; if it's a recurring class, also add to the Repeat-Offenders note.
- **Fix** (`ID_<Fix>_####`): frontmatter `id, type: fix, status, session, date`; link the Issue(s) it resolves
  + the commit; add a row to the Fix index.
- **Feature** (`ID_<Feature>_####`): frontmatter `id, type: feature, domain, area, status: proposed, priority, date`;
  add a row to both the Feature index and the Feature stack; bump the Feature marker. Features are product
  capabilities — **not** bugs; never file them in the Issue stack.
- **Handoff** (`<Session>_####_handoff`) — only on `Session_END`: Done / Outstanding / Refs + one workflow note;
  index it; mark the session `done`; update Open Actions.

## Status-tag lifecycle (portable convention)
Tag notes through their life: **`#idea` → `#spec` → `#building` → `#review` → `#done`**. A session's
"definition of done" = slice runs end-to-end, matches the spec, issues logged + fixed (or carried in the
handoff).

## Invariants
`[[wikilink]]` everything; nothing orphaned. `0000` = template; real IDs start at `0001`. Match the
existing table columns exactly.
