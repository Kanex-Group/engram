# Changelog — engram

`brain-sync` reads this to decide "did the brain improve since this project's last_sync?".
Newest at top. Format: `## [version] — YYYY-MM-DD` then bullets tagged `[A]` (capability) / `[B]` (method) / `[C]` (human layer).

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
