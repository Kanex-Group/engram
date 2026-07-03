---
name: company-layer
description: >-
  Stand up a project's business/company operating layer beside its dev spine — a federation of scoped,
  hard-walled, propose-only function-nodes (CFO, Legal-Ops, HR, Operations, …) coordinated by an AI-CEO and
  surfaced through a single Human-Gate front desk. Use when a project needs business operations (not just
  code) run the brain way. Pairs with obrain-schema, decompose-distribute-tasks.
---

# company-layer  ·  applies-when: a project needs a business/operations layer beside its dev spine

Generalizes the node↔Core propose-only boundary into an **intra-project org of agents**. The company layer
runs business *functions* the same way the dev spine runs *code*: scoped, propose-only, human-gated. Build
only the function-nodes a project actually needs (velocity > ceremony); keep the names/conventions identical
across projects so the brain's skills work everywhere. Node-specific functions/figures/contracts are
Layer-D — they stay node-local, never in Core.

## The five parts
1. **Scoped function-nodes.** Each business function (Finance/CFO · Legal-Ops · HR · Operations · …) is a
   node with a **hard jurisdiction** (reads/writes only its own dir + its one named data source), a
   **propose-only brain**, and a scoped agent definition. It never crosses its wall — anything else → ask the founder.
2. **The CEO / sub-CEO node.** Two-directional aggregation: the human delegates a problem → the CEO opens a
   session ID and delegates the parts to the right function-nodes → it aggregates what they surface →
   dedupe/prioritize → an **executive summary** for the human. It **surfaces calls; the human decides** —
   the CEO never makes the binding call.
3. **The Human-Gate node.** One human-facing **front desk**: read summaries/reports/visuals, **communicate**
   via a drop-point that routes to the CEO, review flagged items. Librarian role — organizes + presents,
   never decides. Maxim: **"delegate through the CEO, read through the Human-Gate."**
4. **Reporting conventions.** CEO-owned session IDs + per-node report IDs + a `Reports/` folder per node +
   a **session-end human-readable digest** pushed to the Human-Gate + per-node **self-checks** + a
   **human-readability standard** (findings-first, plain language).
5. **The readiness gate.** Function-nodes must **proactively** surface *foundational* blockers ("is the
   business even set up to do this?" — incorporation, accounts, payroll, bank) on any operational ask — not
   just answer the narrow question.

## Hard rules
- **Propose-only.** A function-node proposes into its up-facing queue; it never self-applies a binding
  decision. (A stateful agent that writes-and-trusts its own brain self-poisons → propose + a gate.)
- **Hard jurisdiction.** A node touches only its own store + its named source; cross-function need routes
  through the CEO. Layer-D/secret figures stay in the node's confidential store, never in Core.
- **Human overwatch decides.** The CEO surfaces; the founder makes the binding calls.

## Stand one up
Scaffold the store-set per `obrain-schema` (the `C-Suite/` function dirs + per-node `Reports/` + a
`Human-Gate/`), write each node's scoped agent def + propose-only brain, and wire the CEO session-IDs +
Human-Gate dashboard. Build only the functions needed now.

Up: [capabilities.md](../../capabilities.md)
