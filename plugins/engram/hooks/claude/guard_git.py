#!/usr/bin/env python3
"""Engram Tier-1 Claude Code hook: PreToolUse(Bash) git guard.

Intercepts Bash tool calls at tool-call time and DENIES dangerous git actions:

  1. `git push` to a protected branch (including -f / --force / --force-with-lease)
     when no complete QA record is present.
  2. `git commit` whose message carries an AI-authorship fingerprint trailer
     (e.g. "Co-Authored-By: Claude"). A stray AI-authorship trailer once broke a
     real auto-deploy, so these are blocked.
  3. `git add` (or `git commit -a`) that would stage a secret / deny-listed file
     (e.g. *.env, secrets.*).

Anything else is ALLOWED (exit 0, no output -> normal permission flow).

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


def allow():
    """Allow: print nothing, exit 0 (normal permission flow applies)."""
    sys.exit(0)


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
def has_complete_qa_record(cfg, cwd):
    qa = cfg.get("qa", {})
    qa_dir = qa.get("dir", "QA")
    record_glob = qa.get("record_glob", "QA_*.md")
    marker = qa.get("passed_marker", "status: PASSED")
    search_root = os.path.join(cwd or ".", qa_dir)
    # Search the QA dir and one level of nesting.
    patterns = [
        os.path.join(search_root, record_glob),
        os.path.join(search_root, "**", record_glob),
    ]
    files = set()
    for p in patterns:
        files.update(glob.glob(p, recursive=True))
    for f in sorted(files):
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                if marker in fh.read():
                    return True
        except Exception:
            continue
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

    # Ambiguous push (no explicit branch) to a protected branch is common when
    # the current branch IS protected; we cannot read HEAD reliably here, so we
    # treat an explicit protected-branch ref, OR a force with no clear target,
    # as requiring a QA record. A bare `git push` with no refs is allowed
    # (it pushes the current tracking branch, which the pre-push git hook backs up).
    needs_qa = targets_protected or (forced and not refs)

    if not needs_qa:
        return None
    if has_complete_qa_record(cfg, cwd):
        return None

    branch_list = "/".join(protected) or "protected"
    force_note = " (force push) " if forced else " "
    return (
        "Engram guard: blocked git push{fn}to a protected branch ({bl}) with no "
        "complete QA record present. Expected a '{glob}' file under '{dir}/' "
        "containing '{marker}'. Run the pre-merge QA gate first. {bypass}".format(
            fn=force_note,
            bl=branch_list,
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
                return (
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
        return (
            "Engram guard: blocked staging of secret/deny-listed file(s): {off}. "
            "These match a deny_paths pattern and must never be committed. {bypass}".format(
                off=", ".join(offenders), bypass=BYPASS_NOTE
            )
        )
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

    for tokens in split_pipeline(command):
        # Only inspect git invocations.
        if not tokens or os.path.basename(tokens[0]) != "git":
            continue
        reason = check_commit_fingerprint(tokens, command, cfg)
        if reason:
            deny(reason)
        reason = check_push(tokens, cfg, cwd)
        if reason:
            deny(reason)
        reason = check_stage_secret(tokens, cfg)
        if reason:
            deny(reason)

    allow()


if __name__ == "__main__":
    main()
