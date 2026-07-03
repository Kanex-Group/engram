# Getting Started with Engram

Engram gives your AI coding agent **persistent memory**. Instead of re-deriving your
project every session, the agent orients from a local knowledge base — an Obsidian-style
vault (**OBrain**), a set of skills, a library of engineering methods, and an enforcement
hook layer that turns "rules" into things the agent *can't* skip.

It runs **100% locally**. Plain Markdown in your repo plus plugin skills. No telemetry, no
account, no auto-sync. Nothing leaves your machine unless you open a pull request yourself.

This guide takes you from zero to a brain that genuinely knows your project.

---

## 1. What you need

- **[Claude Code](https://claude.com/claude-code)** — Engram is a Claude Code plugin.
- **Python 3** — only for the one-time enforcement-hook installer.
- **Git** — your project should be a git repo (the backstop hooks are git hooks).
- **Obsidian** *(optional)* — nice for viewing/editing the vault as a graph. Not required;
  the vault is just Markdown files, readable in any editor.

The vault lives **outside your repo** (gitignored) by default, so brain notes never
accidentally ship with your code.

---

## 2. Install the plugin

From inside Claude Code:

```
# 1. Add this repository as a plugin marketplace
/plugin marketplace add Kanex-Group/engram

# 2. Install the Engram plugin
/plugin install engram@engram
```

That's it — your agent now has the Engram skills available.

---

## 3. First session

Open a session in any project and run:

```
brain-sync
```

(or just tell the agent "sync the brain"). `brain-sync` is the session-start ritual: it
pulls shared improvements, orients the agent, and proposes any relevant capabilities.

**No vault yet?** The first time, there's nothing to sync — so scaffold one. Ask the agent
to use the **`obrain-schema`** skill:

```
scaffold an OBrain vault for this project using obrain-schema
```

This creates the canonical folder structure — the parts you actually need to start:

- `Home.md` — the master map / entry point.
- `Dev_Sessions/` — the **session spine**: `Sessions/` → `Issues/` → `Fixes/` →
  `Session Handoff/`, plus `Open Actions.md` and the QA gate.
- `Wiki/` + `Raw/` — a derived mirror of your code (built later by `wiki-sync`).
- `Knowledge/`, `Decisions/` — playbooks and ADRs, added as you need them.

> Build only the stores you need yet — velocity over ceremony — but keep the names and
> conventions identical across projects so the skills work everywhere.

---

## 4. Install the enforcement hooks

Skills tell the agent what *should* happen. **Hooks make it happen.** This step is what
turns Engram's conventions from polite suggestions into enforcement.

Run the installer once per project:

```
python plugins/engram/hooks/install.py
```

To remove them later:

```
python plugins/engram/hooks/install.py --uninstall
```

The installer sets up **two tiers of enforcement**, and prints a small Claude Code settings
snippet for you to paste into your project settings:

- **Tier 1 — Harness hooks (catch the agent in the act).** Wired into Claude Code via the
  settings snippet. These fire *during* a session — e.g. a `SessionStart` hook that makes
  "read the vault first" a guarantee, not something the model has to remember. They catch
  mistakes before they land.
- **Tier 2 — Git hooks (the backstop).** Installed into your repo's git hooks. Even if a
  change slips past the agent, these stop it at commit/merge time. Last line of defense.

Paste the printed settings snippet where the installer tells you, restart the session, and
enforcement is live. From here on, the daily loop below isn't optional discipline — the
hooks hold the line for you.

---

## 5. The daily loop

Once you're set up, a normal day looks like this:

1. **Start** — `brain-sync`. The agent orients from the vault, picks up the last
   **Handoff**, and knows where you left off.
2. **Work the spine** — as you go, the agent logs the session as a chain:
   **Session → Issue → Fix → Handoff**. Each is a small Markdown note with a stable ID,
   wiki-linked into the vault. This is the continuity that survives `/clear` and context
   resets.
3. **After code changes** — run **`wiki-sync`** in the *same* session, so the derived
   `Wiki/` mirror of your code never drifts from reality. (The agent reads the wiki instead
   of re-reading your whole source tree next time.)
4. **Before shipping** — run **`pre-merge-check`**. It's a typed QA & merge gate: it opens
   a QA record, runs the checks for your change type (Bug / Feature / Money / Security /
   Infra / …), and **blocks the merge until every applicable box is ticked and you type
   the project's exact approval phrase.** A click or a "yes" is *not* the phrase — that's on
   purpose, so a casual confirmation can't authorize an irreversible merge.

The hooks from step 4 back all of this up.

---

## 6. Worked example: your first bug fix

Say the agent (or you) find a bug where uploads over the size limit crash the server
instead of returning a clean error. Here's the loop end to end:

**1. Open the session and log the issue.** The agent scaffolds an Issue note (via
`new-dev-note`), taking the next free ID from the index:

```
Dev_Sessions/Issues/Issue_0007.md
---
id: Issue_0007
status: #building
session: [[Session_0003]]
---
# Oversized upload crashes the server
Repro: POST a 500 MB file to /ingest → unhandled exception, 500 + stack trace.
Expected: rejected early with a 400.
```

**2. Fix the code.** The agent applies the fix (early size cap → return 400 before the
parser ever runs).

**3. Write the Fix note.** A Fix note records what changed and *why*, linked back to the
issue:

```
Dev_Sessions/Fixes/Fix_0007.md
---
id: Fix_0007
status: #done
fixes: [[Issue_0007]]
---
# Early size cap on /ingest
Added a size check before parsing; oversized uploads now 400 instead of 500.
Regression test: test_ingest_rejects_oversized() — fails before, passes after.
```

**4. Sync the wiki + close out.** Run `wiki-sync` to update the `/ingest` page in `Wiki/`,
then a short Handoff note so the next session starts informed. Run `pre-merge-check` before
this lands on `main`.

Next session, the agent reads `Issue_0007` → `Fix_0007` and *already knows* this endpoint
was hardened and why. That's the whole point.

---

## 7. Day 1 → Day 30

The brain is empty on day one and earns its value over time.

- **Day 1** — Empty vault. You install, scaffold, and `brain-sync` does almost nothing.
  The agent still re-reads your code to understand it. Feels like overhead. That's normal.
- **Week 1** — A handful of Issues and Fixes exist. The `Wiki/` mirror covers the files
  you've touched. Sessions now resume from a real Handoff instead of a cold start. The
  agent stops asking you the same orientation questions.
- **Week 2–3** — Decisions and playbooks accumulate. The agent references *why* something
  is the way it is — not just what the code does. Repeat bugs get caught by the QA gate's
  repeat-offender check. You re-explain your project far less.
- **Day 30** — The vault is a genuine model of your project: its architecture, its
  history, its decisions, its sharp edges. A fresh session — even after `/clear` — orients
  in seconds from the brain instead of re-deriving everything. The agent behaves like it
  *remembers*, because now it does.

The curve is real: it costs a little up front and compounds. The value isn't a token-count
trick — it's **continuity and safety**: work that survives resets, and guardrails that
don't forget.

---

## 8. Privacy & getting help

**Privacy.** Engram runs entirely on your machine. It's Markdown files plus plugin skills —
no telemetry, no analytics, no account, no auto-sync. Nothing is uploaded anywhere. The
human/personal layer ships as a **blank template**; you fill it in locally and it never
leaves your machine. The *only* way anything is shared is if **you** open a pull request.

**Help & contributing.**

- Read the top-level **[README](../README.md)** for the full feature tour and the layer
  model.
- Found a bug or want a feature? Open an issue on the repository.
- Contributions are welcome and **opt-in** — fork, branch off `main`, and open a PR. Every
  merge is reviewed. See **CONTRIBUTING.md** and the **CLA** for details.
- Please never include personal data, secrets, or private project content in a
  contribution.

Now go start a session and run `brain-sync`. By next month your agent won't need the
introduction.
