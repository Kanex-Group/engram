#!/usr/bin/env python3
"""Engram Tier-1 Claude Code hook: PreToolUse(Bash) git guard.

Intercepts Bash tool calls at tool-call time and DENIES (or asks the human to
confirm) dangerous git / migration actions:

  1. `git push` to a protected branch (including -f / --force / --force-with-lease)
     when no complete QA record is present. With config
     ``protected_scope: "all-pushes"``, ANY `git push` to origin is denied
     without a complete QA record (not just protected branches).
  2. `git commit` whose message carries an AI-authorship fingerprint trailer
     (e.g. "Co-Authored-By: Claude"). A stray AI-authorship trailer once broke a
     real auto-deploy, so these are blocked.
  3. `git add` (or `git commit -a`) that would stage a secret / deny-listed file
     (e.g. *.env, secrets.*).
  4. `git branch -d/-D` (branch delete) and `git worktree remove` -> CONFIRM.
  5. DB migrations (`alembic upgrade`, `prisma migrate`, `manage.py migrate`,
     `knex migrate`) -> CONFIRM (destructive/irreversible schema changes).
  6. Bulk staging (`git add -A` / `git add .` / `git add --all`) in a brain repo
     -> CONFIRM (sweeps in secrets / private notes).
  7. Branch-first rule: a file-writing git op (`git commit`, `git add`) while HEAD
     is a protected branch (main/master) -> DENY (work on a branch, not main).

Anything else is ALLOWED (exit 0, no output -> normal permission flow).

Decision severities: a matcher returns either a DENY reason (hard block) or a
CONFIRM reason (ask the human). DENY beats CONFIRM if both fire.

I/O contract (Claude Code PreToolUse hook), verified against the official docs:
  stdin  : JSON, e.g.
             {"hook_event_name":"PreToolUse","tool_name":"Bash",
              "tool_input":{"command":"git push origin main"},"cwd":"/repo", ...}
  stdout : to DENY, a JSON object:
             {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                     "permissionDecision": "deny",
                                     "permissionDecisionReason": "<why + bypass>"}}
           to ALLOW, print nothing.
  exit   : 0 in all normal cases (the JSON on stdout controls the decision).

Config: reads ../engram.hooks.json (sibling of the claude/ dir) if present, else
falls back to built-in defaults identical to the spec. Pure Python 3 stdlib.
Cross-platform. No project/personal data.
"""
import fnmatch
import glob
import json
import os
import re
import shlex
import sys


# ---------------------------------------------------------------------------
# Built-in defaults (used when engram.hooks.json is absent or partial).
# ---------------------------------------------------------------------------
DEFAULTS = {
    "protected_branches": ["main", "master"],
    # "protected-branches" (default, public-safe): only pushes that TARGET a
    # protected branch require a complete QA record.
    # "all-pushes": ANY push to origin requires a complete QA record.
    "protected_scope": "protected-branches",
    "qa": {"dir": "QA", "record_glob": "QA_*.md", "passed_marker": "status: PASSED"},
    "secret_scan": {
        "deny_paths": ["*.env", ".env", "secrets.*", "_dev_core/*", "*.locked"],
        "deny_patterns": [
            r"-----BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY-----",
            r"AKIA[0-9A-Z]{16}",
            r"xox[baprs]-[0-9A-Za-z-]+",
            r"ghp_[A-Za-z0-9]{36}",
            r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}",
        ],
    },
    "fingerprint": {
        "deny_trailers": [
            "Co-Authored-By: Claude",
            "Co-Authored-By: .*anthropic",
            "Generated with .*Claude",
        ]
    },
    # Additional destructive-op matchers (spec "stop-list"). All CONFIRM-level
    # (ask the human) except the branch-first rule, which is a hard DENY.
    "stop_list": {
        # git branch -d/-D and git worktree remove -> confirm.
        "confirm_branch_delete": True,
        "confirm_worktree_remove": True,
        # DB migrations -> confirm. Matched as substrings of the command.
        "confirm_db_migrations": True,
        "db_migration_matchers": [
            r"alembic\s+upgrade",
            r"prisma\s+migrate",
            r"manage\.py\s+migrate",
            r"knex\s+migrate",
        ],
        # `git add -A` / `git add .` / `git add --all` in a brain repo -> confirm.
        "confirm_bulk_add_in_brain": True,
        # A repo is treated as a "brain" repo if any of these marker paths exist
        # at the repo root (relative to cwd). Keep generic + public-safe.
        "brain_markers": [".obsidian", "engram.hooks.json", "OBRAIN.md"],
        # Branch-first: DENY file-writing git ops on a protected branch.
        "deny_write_on_protected_branch": True,
    },
}

BYPASS_NOTE = (
    "If this is a true emergency, a human can run the command manually outside "
    "the agent (the harness only guards agent-issued tool calls)."
)


def _deep_merge(base, override):
    """Shallow-per-key merge: override keys win; nested dicts merged one level."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def load_config():
    """Load engram.hooks.json from the parent of this script's dir, else defaults."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "engram.hooks.json"))
    if os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
            return _deep_merge(DEFAULTS, user_cfg)
        except Exception:
            # Malformed config must not disable the guard: fall back to defaults.
            return dict(DEFAULTS)
    return dict(DEFAULTS)


def deny(reason):
    """Emit the documented PreToolUse deny JSON and exit 0."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    sys.exit(0)


def confirm(reason):
    """Emit a PreToolUse 'ask' decision (human must confirm) and exit 0."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    sys.exit(0)


def allow():
    """Allow: print nothing, exit 0 (normal permission flow applies)."""
    sys.exit(0)


# Severity constants for matcher return values.
DENY = "deny"
CONFIRM = "ask"


# ---------------------------------------------------------------------------
# Command parsing helpers.
# ---------------------------------------------------------------------------
def split_pipeline(command):
    """Split a shell command string into individual simple-command token lists.

    Splits on ; && || | and newlines so `foo && git push ...` is inspected.
    Best-effort: uses shlex; on parse failure, returns a single token list.
    """
    # Normalize the separators shlex won't split on into a sentinel.
    sentinel = "\x00SEP\x00"
    normalized = re.sub(r"(\|\||&&|;|\n|\||&)", sentinel, command)
    segments = [s.strip() for s in normalized.split(sentinel) if s.strip()]
    result = []
    for seg in segments:
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            toks = seg.split()
        if toks:
            result.append(toks)
    return result


def is_git_subcommand(tokens, subcommand):
    """True if tokens is a `git <subcommand> ...` invocation.

    Skips a leading `git` plus any `-c key=val` / global option pairs.
    """
    if not tokens:
        return False
    i = 0
    if os.path.basename(tokens[0]) != "git":
        return False
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-c" or t == "-C" or t == "--namespace":
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t == subcommand
    return False


def git_args_after(tokens, subcommand):
    """Return the args following `git <subcommand>` (excludes the subcommand)."""
    idx = None
    for i, t in enumerate(tokens):
        if t == subcommand:
            idx = i
            break
    if idx is None:
        return []
    return tokens[idx + 1 :]


# ---------------------------------------------------------------------------
# QA record check.
# ---------------------------------------------------------------------------
def _qa_check_tool_path():
    """Path to the shared tools/qa_check.py, or None if it isn't shipped yet."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(
        os.path.join(here, "..", "..", "tools", "qa_check.py")
    )
    return candidate if os.path.isfile(candidate) else None


def _qa_records(cfg, cwd):
    """Yield candidate QA record paths under the configured QA dir."""
    qa = cfg.get("qa", {})
    qa_dir = qa.get("dir", "QA")
    record_glob = qa.get("record_glob", "QA_*.md")
    search_root = os.path.join(cwd or ".", qa_dir)
    patterns = [
        os.path.join(search_root, record_glob),
        os.path.join(search_root, "**", record_glob),
    ]
    files = set()
    for p in patterns:
        files.update(glob.glob(p, recursive=True))
    return sorted(files)


def has_complete_qa_record(cfg, cwd):
    """True if a COMPLETE QA record exists.

    Prefers the shared ``tools/qa_check.py`` completeness checker (built by
    another agent): a record is complete only if qa_check exits 0 for it. If the
    tool is absent, falls back to the historical "exists AND contains the
    passed_marker" grep so this guard keeps working standalone.
    """
    marker = cfg.get("qa", {}).get("passed_marker", "status: PASSED")
    records = _qa_records(cfg, cwd)
    tool = _qa_check_tool_path()

    if tool is not None:
        import subprocess

        for f in records:
            try:
                proc = subprocess.run(
                    [sys.executable, tool, f],
                    capture_output=True,
                    text=True,
                    cwd=cwd or None,
                )
                if proc.returncode == 0:
                    return True
            except Exception:
                # Tool blew up on THIS file only: grep just this one as a fallback.
                try:
                    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                        if marker in fh.read():
                            return True
                except Exception:
                    pass
        # Tool is present and authoritative: no record passed completeness. Do
        # NOT fall back to a bare marker grep — an INCOMPLETE record can still
        # contain the passed_marker, and grepping it would defeat the whole
        # point of checking evidence rather than existence.
        return False

    # Tool absent: historical "exists AND contains the marker" grep fallback.
    for f in records:
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                if marker in fh.read():
                    return True
        except Exception:
            continue
    return False


def current_branch(cwd):
    """Return the current branch name (HEAD), or None if undeterminable."""
    try:
        import subprocess

        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd or None,
        )
        if proc.returncode == 0:
            name = proc.stdout.strip()
            return name or None
    except Exception:
        pass
    return None


def _is_brain_repo(cfg, cwd):
    """True if cwd looks like a brain repo (any configured marker present)."""
    markers = cfg.get("stop_list", {}).get("brain_markers", [])
    root = cwd or "."
    for m in markers:
        if os.path.exists(os.path.join(root, m)):
            return True
    return False


# ---------------------------------------------------------------------------
# Individual guards. Each returns a deny-reason string, or None to allow.
# ---------------------------------------------------------------------------
def check_push(tokens, cfg, cwd):
    if not is_git_subcommand(tokens, "push"):
        return None
    protected = cfg.get("protected_branches", [])
    args = git_args_after(tokens, "push")
    forced = any(a in ("-f", "--force") or a.startswith("--force-with-lease") for a in args)
    positionals = [a for a in args if not a.startswith("-")]
    # positionals typically: [remote, refspec...]. A refspec may be "local:remote".
    refs = positionals[1:] if len(positionals) >= 2 else positionals

    def ref_targets_protected(ref):
        target = ref.split(":")[-1] if ":" in ref else ref
        target = target.rsplit("/", 1)[-1]  # refs/heads/main -> main
        return target in protected

    targets_protected = any(ref_targets_protected(r) for r in refs)

    scope = cfg.get("protected_scope", "protected-branches")
    all_pushes = scope == "all-pushes"

    # Ambiguous push (no explicit branch) to a protected branch is common when
    # the current branch IS protected; we cannot read HEAD reliably here, so we
    # treat an explicit protected-branch ref, OR a force with no clear target,
    # as requiring a QA record. A bare `git push` with no refs is allowed under
    # the default scope (it pushes the current tracking branch, which the
    # pre-push git hook backs up). Under "all-pushes", ANY push to origin needs
    # a complete QA record, including a bare `git push`.
    if all_pushes:
        needs_qa = True
    else:
        needs_qa = targets_protected or (forced and not refs)

    if not needs_qa:
        return None
    if has_complete_qa_record(cfg, cwd):
        return None

    branch_list = "/".join(protected) or "protected"
    force_note = " (force push) " if forced else " "
    if all_pushes:
        target_desc = "origin (protected_scope=all-pushes)"
    else:
        target_desc = "a protected branch ({bl})".format(bl=branch_list)
    return DENY, (
        "Engram guard: blocked git push{fn}to {td} with no "
        "complete QA record present. Expected a COMPLETE '{glob}' file under "
        "'{dir}/' containing '{marker}'. Run the pre-merge QA gate first. "
        "{bypass}".format(
            fn=force_note,
            td=target_desc,
            glob=cfg["qa"]["record_glob"],
            dir=cfg["qa"]["dir"],
            marker=cfg["qa"]["passed_marker"],
            bypass=BYPASS_NOTE,
        )
    )


def check_commit_fingerprint(tokens, command, cfg):
    if not is_git_subcommand(tokens, "commit"):
        return None
    trailers = cfg.get("fingerprint", {}).get("deny_trailers", [])
    # Gather candidate message text: -m/--message values and -F/--file contents.
    args = git_args_after(tokens, "commit")
    messages = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-m", "--message") and i + 1 < len(args):
            messages.append(args[i + 1])
            i += 2
            continue
        if a.startswith("--message="):
            messages.append(a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("-m") and len(a) > 2:
            messages.append(a[2:])
            i += 1
            continue
        i += 1
    # Scan both the parsed -m/--message values AND the raw command string. The
    # raw string is a necessary fallback because a multi-line commit message
    # (real newlines, heredocs) can be split across pipeline segments before it
    # ever reaches this token list. Fingerprint trailers are highly specific, so
    # scanning the raw command does not meaningfully increase false positives.
    haystack = "\n".join(messages) + "\n" + (command or "")
    for pat in trailers:
        try:
            if re.search(pat, haystack):
                return DENY, (
                    "Engram guard: blocked git commit carrying an AI-authorship "
                    "trailer matching /{pat}/. AI-fingerprint trailers are "
                    "forbidden (one once broke an auto-deploy). Remove the trailer "
                    "from the commit message. {bypass}".format(pat=pat, bypass=BYPASS_NOTE)
                )
        except re.error:
            continue
    return None


def _path_is_denied(path, deny_globs):
    base = os.path.basename(path)
    norm = path.replace("\\", "/")
    for g in deny_globs:
        if fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(base, g):
            return True
        # Allow directory-glob like "_dev_core/*" to match nested paths.
        if g.endswith("/*") and (norm == g[:-2] or norm.startswith(g[:-1])):
            return True
    return False


def check_stage_secret(tokens, cfg):
    """Block `git add <secret>` or `git commit -a` touching secret paths."""
    deny_globs = cfg.get("secret_scan", {}).get("deny_paths", [])
    if not deny_globs:
        return None

    staged_paths = []
    if is_git_subcommand(tokens, "add"):
        args = git_args_after(tokens, "add")
        for a in args:
            if a.startswith("-"):
                # `git add -A` / `.` could stage secrets, but we can't enumerate
                # the tree here; the Tier-2 pre-commit hook is the backstop for
                # that. We only hard-deny explicitly named secret paths.
                continue
            staged_paths.append(a)
    elif is_git_subcommand(tokens, "commit"):
        # `git commit -a` stages tracked modifications; explicit pathspecs too.
        args = git_args_after(tokens, "commit")
        for a in args:
            if a.startswith("-"):
                continue
            staged_paths.append(a)

    offenders = [p for p in staged_paths if _path_is_denied(p, deny_globs)]
    if offenders:
        return DENY, (
            "Engram guard: blocked staging of secret/deny-listed file(s): {off}. "
            "These match a deny_paths pattern and must never be committed. {bypass}".format(
                off=", ".join(offenders), bypass=BYPASS_NOTE
            )
        )
    return None


def check_branch_delete(tokens, cfg):
    """`git branch -d/-D <name>` -> CONFIRM (branch deletion is destructive)."""
    if not cfg.get("stop_list", {}).get("confirm_branch_delete", True):
        return None
    if not is_git_subcommand(tokens, "branch"):
        return None
    args = git_args_after(tokens, "branch")
    # -d/-D, or their combined/long forms (-dr, --delete, --delete --force ...).
    deleting = any(
        a in ("-d", "-D", "--delete")
        or (a.startswith("-") and not a.startswith("--") and ("d" in a or "D" in a))
        for a in args
    )
    if not deleting:
        return None
    targets = [a for a in args if not a.startswith("-")] or ["<branch>"]
    return CONFIRM, (
        "Engram guard: `git branch -d/-D` deletes branch(es): {t}. Confirm you "
        "have merged or no longer need this work -- deleted local branches are "
        "not trivially recoverable. {bypass}".format(
            t=", ".join(targets), bypass=BYPASS_NOTE
        )
    )


def check_worktree_remove(tokens, cfg):
    """`git worktree remove <path>` -> CONFIRM (drops a working tree)."""
    if not cfg.get("stop_list", {}).get("confirm_worktree_remove", True):
        return None
    if not is_git_subcommand(tokens, "worktree"):
        return None
    args = git_args_after(tokens, "worktree")
    if not args or args[0] != "remove":
        return None
    targets = [a for a in args[1:] if not a.startswith("-")] or ["<path>"]
    return CONFIRM, (
        "Engram guard: `git worktree remove` drops working tree(s): {t}. Confirm "
        "any uncommitted work there is expendable. {bypass}".format(
            t=", ".join(targets), bypass=BYPASS_NOTE
        )
    )


def check_db_migration(command, cfg):
    """DB migration commands (alembic/prisma/manage.py/knex) -> CONFIRM."""
    sl = cfg.get("stop_list", {})
    if not sl.get("confirm_db_migrations", True):
        return None
    for pat in sl.get("db_migration_matchers", []):
        try:
            if re.search(pat, command or ""):
                return CONFIRM, (
                    "Engram guard: DB migration detected (matched /{pat}/). "
                    "Schema migrations are often irreversible and can affect "
                    "production data. Confirm the target DB/environment before "
                    "running. {bypass}".format(pat=pat, bypass=BYPASS_NOTE)
                )
        except re.error:
            continue
    return None


def check_bulk_add_in_brain(tokens, cfg, cwd):
    """`git add -A` / `git add .` / `--all` in a brain repo -> CONFIRM."""
    sl = cfg.get("stop_list", {})
    if not sl.get("confirm_bulk_add_in_brain", True):
        return None
    if not is_git_subcommand(tokens, "add"):
        return None
    args = git_args_after(tokens, "add")
    bulk = any(
        a in ("-A", "--all", ".", "-a") or a == "--no-ignore-removal" for a in args
    )
    if not bulk:
        return None
    if not _is_brain_repo(cfg, cwd):
        return None
    return CONFIRM, (
        "Engram guard: bulk `git add` (-A/./--all) in a brain repo stages every "
        "changed file, which can sweep in private notes or secrets. Confirm, or "
        "stage explicit paths instead. {bypass}".format(bypass=BYPASS_NOTE)
    )


def check_write_on_protected_branch(tokens, cfg, cwd):
    """Branch-first: DENY `git commit` / `git add` while HEAD is protected."""
    sl = cfg.get("stop_list", {})
    if not sl.get("deny_write_on_protected_branch", True):
        return None
    is_commit = is_git_subcommand(tokens, "commit")
    is_add = is_git_subcommand(tokens, "add")
    if not (is_commit or is_add):
        return None
    branch = current_branch(cwd)
    if branch is None:
        return None  # can't determine HEAD -> don't block
    protected = cfg.get("protected_branches", [])
    if branch not in protected:
        return None
    op = "git commit" if is_commit else "git add"
    return DENY, (
        "Engram guard: branch-first rule -- blocked `{op}` while HEAD is the "
        "protected branch '{br}'. Create/switch to a feature branch first "
        "(e.g. `git switch -c <branch>`), then stage/commit there. {bypass}".format(
            op=op, br=branch, bypass=BYPASS_NOTE
        )
    )


def evaluate(command, cfg, cwd):
    """Run all matchers; return (severity, reason) or None.

    A DENY from any matcher wins over a CONFIRM. Within the same severity, the
    first match wins.
    """
    deny_reason = None
    confirm_reason = None

    def record(result):
        nonlocal deny_reason, confirm_reason
        if not result:
            return
        sev, reason = result
        if sev == DENY and deny_reason is None:
            deny_reason = reason
        elif sev == CONFIRM and confirm_reason is None:
            confirm_reason = reason

    for tokens in split_pipeline(command):
        # Command-level (non-git) matcher: DB migrations may be `python manage.py`
        # or an `npx prisma` invocation, so match on the raw segment string too.
        seg = " ".join(tokens)
        record(check_db_migration(seg, cfg))

        if not tokens or os.path.basename(tokens[0]) != "git":
            continue
        record(check_commit_fingerprint(tokens, command, cfg))
        record(check_push(tokens, cfg, cwd))
        record(check_stage_secret(tokens, cfg))
        record(check_branch_delete(tokens, cfg))
        record(check_worktree_remove(tokens, cfg))
        record(check_bulk_add_in_brain(tokens, cfg, cwd))
        record(check_write_on_protected_branch(tokens, cfg, cwd))

    if deny_reason is not None:
        return DENY, deny_reason
    if confirm_reason is not None:
        return CONFIRM, confirm_reason
    return None


def main():
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        # If we can't parse the hook payload, do not block (fail open for
        # non-git / malformed input); the Tier-2 git hooks are the backstop.
        allow()

    if data.get("tool_name") != "Bash":
        allow()

    command = (data.get("tool_input") or {}).get("command", "")
    if not command or not command.strip():
        allow()

    cwd = data.get("cwd") or os.getcwd()
    cfg = load_config()

    result = evaluate(command, cfg, cwd)
    if result is not None:
        sev, reason = result
        if sev == DENY:
            deny(reason)
        else:
            confirm(reason)

    allow()


if __name__ == "__main__":
    main()
