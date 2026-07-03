---
name: learn-mode
description: >-
  How to run "learn mode" with the founder. Use when the human says "learn mode", "let's learn",
  "let's go to learn", or points at a Learn prompt. Go to the project's Learn/ folder, work the LP_#
  prompts together (discuss → converge → THEN implement — never jump straight to building), and record
  converged decisions. Pairs with visualize-mode.
---

# learn-mode  ·  applies-when: any project

When the human says **"learn mode" / "let's learn"** (or a clear equivalent — they deliberately won't
always spell out the trigger; recognizing the cue is the point), go to the project's **`Learn/` folder**.

## Structure
- `Learn/User_Learn_Prompts/LP_#.md` — **founder-authored** learn prompts (LP_0, LP_1, …). Each is a
  topic to **discuss → nail down together → THEN implement** (the notes say so — do NOT jump to building).
- `Learn/Claude_Notes/LP_#_decisions.md` — where **converged decisions** are recorded (write this only
  after you and the human agree).
- `Learn/Claude_Notes/Learn_Ticket_#.md` — **Claude Learn Tickets**: things *I* want to learn/align, status
  `proposed` until the human triages and picks one; then run it like an LP. Don't start a learn ticket unsolicited.

## The ritual
1. **Read the LP** the human points at (or the newest). Reflect the idea back in your own words.
2. **Surface gaps, options, trade-offs**; ground it in real cases from the codebase. Give a recommendation,
   not an exhaustive survey.
3. **Converge** with the human (often over several turns). Use `visualize-mode` if the discussion is dense.
4. **Only then implement** into the OB structure (policy notes, skills, indexes) and **record** the
   converged decisions to `Learn/Claude_Notes/LP_#_decisions.md`.

> Mirror direction: surface your own learning as **learn** tickets, but wait for the human to pick one.
