---
name: vault-lint
description: >-
  Run the Lint operation of the OBrain LLM-Wiki pattern: health-check the vault for broken wikilinks,
  orphan notes, stale paths in skills/CLAUDE.md, stale file:line citations, and Wiki-vs-code drift.
  Use on request ("lint the vault", "vault health check") or periodically. Fixes mechanical issues;
  FLAGS judgement calls for the human. Read-only on authored stores.
---

# vault-lint  ·  applies-when: project has an OBrain vault

The **Lint** op of the LLM-Wiki pattern. The Wiki's #1 risk is going stale; Lint is the periodic sweep
that catches it.

## Checks
1. **Broken wikilinks** — `[[target]]` whose basename has no matching `.md` in the vault.
2. **Orphan notes** — notes with no inbound wikilink (excluding `Home` and `*0000*` templates).
3. **Stale paths in skills/CLAUDE.md** — backticked `Folder/Note.md` references (in the project's `CLAUDE.md`
   + every `SKILL.md`) that no longer resolve. Catches **moved** notes — the basename can be right while the
   folder is wrong.
4. **Stale `file:line` citations** — notes citing a repo path / `file:line` that no longer exists.
5. **Wiki-vs-code drift** — a `Wiki/` page whose described models/endpoints/handlers no longer match the
   code (pairs with `wiki-sync` / Ingest).
6. **Weak cross-refs** — a note that should link a sibling (same app/topic) but doesn't.

Checks 1–3 can be automated by a committed script; 4–6 need a reading pass.

## Rules
- **Scope guard (read-only on authored stores):** Lint may *read* and *flag* anything, but only **fixes**
  files in `Wiki/`. Issues in authored stores (`Decisions/`, `Confidential/`, `Compliance/`, `Knowledge/`,
  `Main Defi/`) are **reported for the human**, never auto-edited.
- **Fix mechanical, flag judgement.** Broken link / moved path / typo → fix. "Is this claim still true / the
  right decision" → flag.
- **Feed the self-optimizer:** material or recurring findings get a row in the Optimization Log.
- **Log it (Lint):** append one line to `log.md` → `## [YYYY-MM-DD] lint | <counts> → <action>`.

> **Portable gotcha (Windows / PowerShell 5.1):** the default `Get-Content` decodes UTF-8 as CP1252 and
> mangles em-dashes (e.g. `Wiki — <app>` pages) into false broken-link/orphan hits. Any lint script must
> read files with `[System.IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)` and stay **pure-ASCII** so PS
> parses it regardless of BOM. Ignore benign dev-note ID placeholders (e.g. `ID_<type>_####`) inside
> `0000` templates. **Also ignore private-memory references** — `memory:slug` plain text and any
> `[[memory-slug]]` pointer: private memory lives *outside* the vault, so these are intentional soft-pointers,
> not broken links (convention: write them as plain `memory:slug`).
