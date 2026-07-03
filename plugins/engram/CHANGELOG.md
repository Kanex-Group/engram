# Changelog — engram

`brain-sync` reads this to decide "did the brain improve since this project's last_sync?".
Newest at top. Format: `## [version] — YYYY-MM-DD` then bullets tagged `[A]` (capability) / `[B]` (method) / `[C]` (human layer).

## [1.2.2] — 2026-07-03
- Repositioning: descriptions now lead **guardrails-first** — "persistent memory *and guardrails* for AI
  coding agents; your agent remembers your project and can't quietly break it." The enforcement layer
  (secret-scan, QA merge-gate, branch/push guards) is the differentiator, so it leads. README tagline +
  both manifests updated. No functional change.

## [1.2.1] — 2026-07-03
- Fix: the secret pre-commit scanner flagged its **own** `_selftest.py` fixtures (which contain deliberately
  fake credentials to test the scanner) — a self-referential false-positive that blocked installers' first
  commit. It now skips `*_selftest.py` by default (configurable via `secret_scan.skip_globs`); real files are
  still scanned. Found by dogfooding the hooks on a live repo.
- Docs: **beginner-friendly getting-started** — a 60-second TL;DR ("tell your agent *set up Engram*"),
  a plain-English tool cheat-sheet, and a `brain doctor` "is it healthy?" check. README points new users
  straight to it. Goal: usable with little-to-no prior experience.

## [1.2.0] — 2026-07-03
Turns methodology into enforcement — the tools/hooks from a full 4-lens optimization audit.
- **Dev-spine CLIs:** `brain-id` (atomic next-ID allocator + marker bump) and `brain-note` (deterministic
  Session/Issue/Fix/Feature note scaffolder) — collision-proof IDs, no more hand-bumping a marker.
- **Ledgers & gate:** `offender_ledger` (append-only repeat-offender tally), `qa_check` (QA-record
  *completeness* parser) — now wired into the merge-gate so a push to a protected branch is blocked unless
  the QA record is COMPLETE (status PASSED **and** no unticked boxes), not merely present.
- **Lints:** `vault_lint` (broken wikilinks / orphans / stale paths), `parity_check` (capabilities↔skills),
  `version_canon` (version consistency), `money_path_lint` (unlocked money-path heuristic),
  `upload_lint` (5-guard upload check).
- **Health & install:** `brain_doctor` (aggregate "is the harness armed?" CLI) + `install.py --check`.
- **New Claude Code hooks:** stop-list guard extensions (branch/worktree delete, DB migrations, `git add -A`,
  branch-first, configurable `protected_scope`), `spawn_log` (PostToolUse sub-agent observability),
  `stop_verify` (non-blocking self-verify nudge), `money_inject` (edit-time money-path checklist).
- **Ops tools:** `deploy_smoke` (content assertion, not just HTTP 200), `wiki_drift`, `changelog_check`.
- **Tamper-evidence:** `seal.py` generalized to protect any configured append-only file (dev-spine indexes,
  money ledgers), not just governance.
- Secret pre-commit scan extended to DB/vault file paths. All tools pure-stdlib, cross-platform, self-tested.

## [1.1.0] — 2026-07-03
- **Enforcement hook layer** — turns rules from prose into harness/git enforcement. Two tiers:
  - **Claude Code hooks** (`hooks/hooks.json`): `SessionStart` brain-first orientation; `PreToolUse(Bash)`
    guard that **denies** `git push` to a protected branch without a passing QA record, blocks commits
    carrying an AI-authorship trailer, and blocks staging secret files.
  - **Git hooks** (`hooks/git/`): `pre-commit` secret/PII scan, `commit-msg` fingerprint block, `pre-push`
    merge-gate — a backstop for any committer. Config-driven via `hooks/engram.hooks.json` (falls back to
    built-in defaults). One-command `hooks/install.py` (+ `--uninstall`).
- **Tools** — generalized, config-driven `tools/seal.py` (seal/tamper-evidence for a local private dir) and
  `tools/digest.py` (what-changed-since-last-review).
- **`docs/GETTING-STARTED.md`** — first-session → day-30 walkthrough.
- **Method:** `pre-merge-check` gains a "what counts as a merge (no exemptions)" clause — first publish /
  first push of a new or public repo is a merge and runs the full gate.

## [1.0.0] — 2026-07-03
- First public open-source release under AGPL-3.0.
- **13 capability skills (Layer A):** `brain-sync`, `vault-lookup`, `new-dev-note`, `wiki-sync`,
  `vault-lint`, `pre-merge-check`, `money-path-guard`, `company-layer`, `brain-first-hook`,
  `harden-upload`, `local-first-rag-stack`, `deploy-release`, `debug-triage`.
- **Methods (Layer B):** `obrain-schema`, `learn-mode`, and the encoded QA-merge-gate / LLM-Wiki-ops /
  session-spine patterns.
- **Human layer (Layer C):** ships as a template — fill it in locally; it never leaves your machine.
- Runs 100% locally. No telemetry, no auto-sync. Contributing is opt-in via pull request.
