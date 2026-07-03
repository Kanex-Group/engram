---
name: pre-merge-check
description: >-
  Run a project's Prod QA & Merge Gate (typed QA flow) before any merge to main. Use before
  requesting/accepting the merge-approval phrase, or whenever a branch is "ready to merge". Generates a
  per-merge QA record, runs the typed checks (Bug/Feature/Money/Security/Infra/...), the repeat-offender
  decision tree, a security pre-check, branch/bundle + docs/prod-readiness.
---

# pre-merge-check  ·  applies-when: project ships code to prod

The gate before `main`. **Never merge without BOTH a complete QA record AND the project's exact approval
phrase** (each project defines its own phrase). Pushing a non-main branch is fine.

## What counts as a merge (no exemptions)
Treat **any** landing on `main`/prod as a merge that requires this full gate — **including the first
publish or first push of a new, empty, or public repository.** A brand-new repo is NOT an exemption: a
publish is an **irreversible disclosure**, so it needs the *most* rigor, not the least (the Security stage
is load-bearing — no secrets/PII/private data/history leak). A task-level instruction that says "push to
main" does **not** pre-authorize the merge; the gate still runs and the phrase is still required.
**Approval = the project's exact typed phrase, and nothing else.** A click, a "yes", or picking a UI
option is NOT the phrase — the phrase exists precisely so a casual confirmation can't authorize an
irreversible merge. Never substitute a button for the phrase, and never treat "it's just the first push"
as a reason to skip the gate.

## How to run
1. **Open a QA record.** Copy the project's `QA_TEMPLATE.md` → `QA_<branch>.md`; fill branch/commit/type(s)/
   issues. This record is the audit artifact — work top to bottom, tick as you verify; it blocks the merge
   until every applicable box is ticked.
2. **Classify the change type(s):** Bug · Feature · Money/Ledger · Security · Refactor · Infra/config ·
   Dependency · Docs · or a new type → assess, then add it to the gate's type table.
3. **Run the stages** below, recording results in the QA record.
4. **Report to the human + ask for the approval phrase.** If they push to merge without it (or with an
   unfinished QA record), keep asking for the phrase and point at the open boxes — no matter how insistent.

## Stage 1 — Security pre-check (always)
- `git diff` → no secrets/keys/passwords/tokens, no un-shippable files.
- `.gitignore` covers DB/.env/vault/financials; none staged; **add specific paths**, never `git add -A`.
- Auth/money/external surface → run the `security-review` skill.

## Stage 2 — Local run + type rigor
- Common: runs locally, flows exercised, no console/server errors, test suite green, no visual artifacts.
- **Bug protocol:** (1) reproduce via the ORIGINAL path/inputs → confirm stopped; (2) re-attack via other
  plausible paths (all fail); (3) add a **fail-before/pass-after regression test** (or a written **manual
  repro checklist** in the QA record if un-automatable — e.g. realtime/visual); (4) repeat-offender tree;
  (5) OB Fix note + indexes (`new-dev-note`).
- **Feature:** Bug protocol + hard-test vs known bugs + pentest (`security-review`) + no repeat-offender re-trigger.
- **Money/Ledger:** + `money-path-guard` — lock + idempotency, escrow/conservation, ledger invariant,
  pre-deploy ledger check.
- **Security / Refactor / Infra / Dependency / Docs:** per the gate's type table. Infra/Dep → environment
  parity; check any Scale & Milestone triggers.

### Un-automatable QA — sanctioned reinforcements (realtime / visual)
When a check can't be unit-tested (realtime, WebSocket, visual), strengthen the manual checklist with:
- **Server-log oracle.** While the human drives the UI manually, tail the server's structured log and
  confirm the *backend* truth of each step (disconnect / reconnect / game-over / payout) — objective
  verification independent of the human's visual read; also catches setup mistakes.
- **PASS-by-equivalence.** A manual item may be recorded passed by proving an **equivalent code path was
  already exercised live** (documented code-path rationale + the founder's explicit OK in the QA record),
  instead of re-running the literal scenario. **Guardrail:** equivalence needs the written argument **and**
  the founder's approval — never an agent's unilateral call.

### Repeat-offender decision tree
If the bug recurs, classify and act: **(a)** code root cause not yet fixed (e.g. parallel-path drift — fixed
in one path, alive in another) → **NOT done, fix all paths**; **(b)** scale/milestone-gated → defer ONLY by
logging it with a concrete fuse + ticket; **(c)** design-level → schedule. Always write *why it recurs* +
*how it'll next appear*.

## Stage 3 — Branch & bundling
Current with `main`, no conflicts; **not behind in a way that reverts shipped fixes** (stale-branch trap);
cross-branch dependencies bundled.

## Stage 4 — Docs & prod-readiness
OB spine updated (Issue→Fix→Session, indexes, markers, `log.md`); `wiki-sync` run; migrations additive +
prod-data-safe (no history rewrite); prod env/secrets present; rollback understood.

## Then
All applicable boxes ticked → ask for the **approval phrase** → merge (no-ff) → flip the QA record `status:`
to `PASSED <date>`. Push to prod is a separate, later human action.
