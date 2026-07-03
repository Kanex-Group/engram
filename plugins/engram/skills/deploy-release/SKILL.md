---
name: deploy-release
description: >-
  The CTO release method — ship to prod safely: an exact-phrase deploy gate, a scoped release agent that
  preps-then-executes, deploy-time data hygiene, local-run/demo verification, and a required-vs-built audit.
  Use when merging/deploying to prod. Pairs with pre-merge-check, money-path-guard.
---

# deploy-release  ·  applies-when: a project ships code to prod

The discipline around the moment of shipping (sits on top of `pre-merge-check`'s approval-phrase gate).

## 1 · Exact-phrase deploy gate
A prod deploy (merge → push) is authorized **only by a literal, pre-agreed approval phrase** typed by the
owner — an acronym/intent is NOT the phrase. The phrase authorizes **both** the no-ff merge(s) **and** the
push, in one go. Never push without it.

## 2 · Spawn a CTO agent to run the deploy
Delegate the release to a scoped agent that: **(a)** locates the repo, verifies branch/main state + stacking +
clean tree, runs the test/QA count — and **reports readiness WITHOUT merging/pushing**; then **(b)** on the
owner's gate phrase, executes the ordered no-ff merges + push and **reports back commit SHAs + push range +
provenance/no-fingerprint verification.**

## 3 · Deploy-time data hygiene
Ensure **migrations AND any required seed run on deploy** (release-phase, not just web-boot — confirm the
platform honors it). **Then verify the live page actually serves data** — an empty table renders a fine-looking
200. If the platform skips the seed, run it once against prod, **idempotently**.

## 4 · Local-run / demo verification
Env-driven settings → point at a **disposable demo DB** → migrate + seed → run → **render the real page
end-to-end** (auth as a demo user; a 200 can be an empty-state). Stop the server cleanly when done.

## 5 · Required-vs-built audit
To answer "is X built to the degree required?": pull the **spec** and the **implementation** separately, map
each required piece to ✅ done / 🟡 partial / ❌ missing / ⚪ deferred-by-design, give a **verdict with honest
caveats**, and **cite where each fact was found.**

> Provenance: every commit carries a `Brain:` trailer, **no AI fingerprint** (it breaks auto-deploy) — verify
> both before pushing.

Up: [capabilities.md](../../capabilities.md)
