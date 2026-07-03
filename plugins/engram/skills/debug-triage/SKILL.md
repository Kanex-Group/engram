---
name: debug-triage
description: >-
  Investigation craft for "why is this broken / is it really done": infra-vs-code triage by error shape,
  claims-vs-reality re-review, the frontend↔backend ID contract, bundle isolation, verify-the-artefact,
  sandbox+clean-delete tests, and right-sizing detection problems. Use when debugging or auditing "done"
  work. Pairs with pre-merge-check.
---

# debug-triage  ·  applies-when: debugging, or auditing whether work is really done

## Triage by symptom
- **Infra-vs-code by error shape** — if an endpoint's error **changes shape across attempts** (404 → 500),
  suspect **infrastructure before code**: port collision, or a dev proxy returning 500 because the backend it
  proxies to is down. Check what's actually listening on the port first.
- **Frontend↔backend ID contract** — resolve entities by the identifier the **frontend actually sends** (a
  code-slug), not by assuming *numeric = primary key*. All-numeric business codes collide with pk heuristics
  and silently return nothing.

## Auditing "done" work
- **Claims-vs-reality re-review** — re-audit "finished" code for (a) **advertised-but-unimplemented**
  capabilities (a `supports_X = True` flag with no impl) and (b) **uncaught-exception → 500** classes.
- **Verify the artefact, not the assumption** — don't trust "tests pass" / "200 OK"; render the actual page,
  open the actual file, read the real state. The win is catching what the narrow check missed.

## Build & test hygiene
- **Bundle isolation** — isolate a large vendor import into its **own cacheable chunk**; avoid over-splitting
  (circular-chunk trap); **document** a raised size limit rather than masking it; deep refactors are visual-gated.
- **Sandbox + clean-delete tests** — run a "what-if" in a **deletable, self-contained container** (own folder,
  own IDs); on the deletion trigger, remove it and **verify zero residue**. Keep the *lesson*, delete the *data*.

## Judgment
- **Right-size detection-type problems** — for adversarial/integrity problems, recognize when detection isn't
  the primary lever (economics/incentives/regulation often are). Build the **spine** (capture→score→flag→
  review→dispute→retain) in shadow mode so launch is a config flip; **don't over-invest** in detection you
  can't calibrate without real data ("build the slot, train later").

Up: [capabilities.md](../../capabilities.md)
