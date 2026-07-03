# Engram enforcement hooks

Engram turns "rules the agent is supposed to remember" into **things the harness
enforces**. There are two independent tiers — install both for defence in depth.

| Tier | Fires for | Mechanism | Events |
|------|-----------|-----------|--------|
| **Tier 1 — Claude Code** | the *agent*, at tool-call time | `.claude/settings.json` `hooks` | `SessionStart`, `PreToolUse` |
| **Tier 2 — Git** | *any* committer (human or tool) | `core.hooksPath` → `hooks/git/` | `pre-commit`, `commit-msg`, `pre-push` |

Tier 1 catches the model before it runs a shell command. Tier 2 is the backstop:
even a plain `git` invocation outside Claude Code is checked. Everything is pure
Python 3 stdlib and cross-platform (Windows / macOS / Linux).

## What each tier enforces

Both tiers read the shared config `hooks/engram.hooks.json` (falling back to
built-in defaults if it's absent):

- **Secret / PII scan** — blocks staged files whose *path* matches a deny glob
  (`*.env`, `secrets.*`, `*.locked`, …) or whose *added content* matches a
  secret regex (private keys, AWS keys, Slack/GitHub tokens, `password=…`).
- **Authorship fingerprint** — blocks commit messages carrying an AI-authorship
  trailer (`Co-Authored-By: Claude`, `Generated with … Claude`, …). Rationale:
  such a trailer once broke a real auto-deploy pipeline.
- **Merge gate** — blocks a push to a protected branch (`main` / `master`)
  unless a complete QA record exists (a file matching `qa.record_glob` under
  `qa.dir` containing `qa.passed_marker`).

Tier 1 additionally injects a **brain-first orientation** at `SessionStart` and
denies the same dangerous `git` commands at `PreToolUse`.

## The shared config: `engram.hooks.json`

```json
{
  "protected_branches": ["main", "master"],
  "qa": { "dir": "QA", "record_glob": "QA_*.md", "passed_marker": "status: PASSED" },
  "secret_scan": {
    "deny_paths": ["*.env", ".env", "secrets.*", "_dev_core/*", "*.locked"],
    "deny_patterns": ["-----BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY-----", "..."]
  },
  "fingerprint": { "deny_trailers": ["Co-Authored-By: Claude", "..."] }
}
```

Edit it to match your repo — add your own protected branches, QA layout, deny
paths, or trailers. If the file is missing, every script uses the built-in
defaults shown above, so the hooks still work out of the box.

> The **seal / digest tools** (`../tools/`) use a *separate* config,
> `engram.config.json` (see `../tools/engram.config.example.json`). Keep them
> distinct: `engram.hooks.json` drives the git/Claude hooks; `engram.config.json`
> drives `seal.py`.

## Install

```sh
# from anywhere inside the target repo:
python /path/to/plugins/engram/hooks/install.py
```

This:

1. Sets the repo's `core.hooksPath` to the shipped `hooks/git/` directory
   (backing up any previous value so `--uninstall` can restore it).
2. Prints the Claude Code settings snippet and tells you to paste it into
   `.claude/settings.json`.

It is **idempotent** — re-running it is safe.

If `core.hooksPath` is already used by another tool, install the git hooks by
copying instead:

```sh
python install.py --copy
```

(`--copy` doesn't auto-update when the plugin changes; re-run to refresh.)

To print just the Claude Code snippet:

```sh
python install.py --print-snippet
```

### Verify it's live

```sh
git commit --allow-empty -m "test"        # runs pre-commit / commit-msg
```

## Uninstall

```sh
python install.py --uninstall
```

Reverts `core.hooksPath` to its prior value (or unsets it). Remove the Engram
`hooks` block from `.claude/settings.json` yourself to disable Tier 1, and if you
used `--copy`, delete the copied files from `.git/hooks`.

## Emergency bypass

The git hooks are a safety net, not a jail. In a genuine emergency you can skip
them — but this is **discouraged** and every block message says so:

```sh
git commit --no-verify ...     # skip pre-commit + commit-msg
git push   --no-verify ...     # skip pre-push
```

There is no bypass flag for Tier 1: to override a Claude Code denial, fix the
underlying issue (remove the secret, drop the fingerprint trailer, complete the
QA record) or run the git command yourself in a terminal outside the harness.
Prefer fixing the cause over bypassing the check.
