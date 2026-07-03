---
name: money-path-guard
description: >-
  Guardrail before editing money/concurrency code in any project that handles real money — payments,
  wallets, ledgers, payouts, or any path that decides a balance-changing result. Surfaces the
  lock + idempotency + ledger-invariant pattern so you don't reintroduce a double-payout. Use whenever
  changing payout, wallet, ledger, or result-deciding code.
---

# money-path-guard  ·  applies-when: project handles real money

The most dangerous repeat offender in any money system is the **unlocked money path**. Before editing
money/result code, apply this. (A project keeps its own live unlocked-path list + known-good examples in its
**Concurrency & Money Playbook** — this Core skill carries the portable rule, not project-specific file:lines.)

## The rule
Any path that **pays out, credits/debits a balance, or decides a balance-changing result** MUST:
1. `transaction.atomic()` (or the stack's equivalent transaction),
2. lock the rows first — `select_for_update()` on the contested rows (game/order + both wallets, or the
   purchase row) **before reading**,
3. re-check the **idempotency guard** (e.g. `payout_done` / purchase `status`) **inside** the txn,
4. write an append-only **ledger row** with the conservation invariant `balance_before + amount = balance_after`,
5. take locks in a **consistent global order** (e.g. by user_id) to avoid cross-transaction deadlock.

Route everything through a **single payout/settlement funnel** rather than duplicating the logic per path.

## Before committing
- Run `pre-merge-check` (Money/Ledger type).
- Add a **concurrency test** if none exists for the path (money surfaces are often untested).
- Confirm no parallel path bypasses the funnel (the classic repeat-offender: fixed in one path, alive in
  another).
