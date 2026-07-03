#!/usr/bin/env python3
"""Engram Claude Code hook: PreToolUse(Edit|Write) money-path checklist injector.

When an Edit/Write targets a file on the configured "money path" list (payments,
wallets, ledgers, payouts -- anything that decides a balance-changing result),
inject the lock + idempotency + ledger-invariant checklist as CONTEXT so the
agent is reminded of the pattern before it writes. The edit is ALWAYS ALLOWED;
this hook only adds a reminder. It NEVER blocks.

  stdin  : JSON PreToolUse payload, e.g.
             {"hook_event_name":"PreToolUse","tool_name":"Edit",
              "tool_input":{"file_path":"src/wallet/payout.py", ...},"cwd":"/repo"}
  stdout : if the path matches a money_paths glob, allow-with-context JSON:
             {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                     "permissionDecision": "allow",
                                     "permissionDecisionReason": "<checklist>",
                                     "additionalContext": "<checklist>"}}
           otherwise nothing (normal permission flow).
  exit   : 0 always.

Config (engram.hooks.json, optional; built-in defaults if absent/broken):
  "money_paths": ["**/wallet/**", "**/ledger/**", "**/payout*", ...]
       -- EMPTY BY DEFAULT (list of []). Empty = this hook is a strict no-op, so
          projects with no money paths get zero noise. Populate to opt in.
  "money_inject": { "enabled": true, "message": "<override checklist>" }

Globs are matched against the file path (both the full normalized path and its
basename), using fnmatch with recursive "**" support.

Pure Python 3 stdlib. Cross-platform. No project/personal data.
"""
import fnmatch
import json
import os
import sys


DEFAULT_CHECKLIST = (
    "Engram money-path guard (reminder only -- your edit is allowed): this file "
    "is on the money path. Before changing balance-deciding logic, confirm the "
    "three invariants:\n"
    "  1. LOCK: the balance read+write is inside a row/account lock or an atomic "
    "compare-and-set (no read-modify-write race; no double-spend window).\n"
    "  2. IDEMPOTENCY: the operation is keyed by an idempotency/request id so a "
    "retry or duplicate delivery cannot pay/charge twice.\n"
    "  3. LEDGER INVARIANT: every balance change is a double-entry ledger write; "
    "sum of entries stays conserved and is the source of truth (not a mutable "
    "balance column). Never delete/rewrite ledger history.\n"
    "If any of these is not already guaranteed on this path, add it before you "
    "ship. A missing lock once caused a real double-payout."
)

DEFAULTS = {
    # Empty by default => no-op. Projects opt in by listing their money paths.
    "money_paths": [],
    "money_inject": {
        "enabled": True,
        "message": DEFAULT_CHECKLIST,
    },
}


def _deep_merge(base, override):
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
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "engram.hooks.json"))
    if os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
            return _deep_merge(DEFAULTS, user_cfg)
        except Exception:
            return dict(DEFAULTS)
    return dict(DEFAULTS)


def path_matches(file_path, money_globs):
    """True if file_path matches any money glob (full path or basename)."""
    if not file_path or not money_globs:
        return False
    norm = file_path.replace("\\", "/")
    base = os.path.basename(norm)
    for g in money_globs:
        gg = g.replace("\\", "/")
        if fnmatch.fnmatch(norm, gg) or fnmatch.fnmatch(base, gg):
            return True
        # Let "**/x/**" also match when x is at the root (zero leading dirs).
        if gg.startswith("**/"):
            trimmed = gg[3:]
            if fnmatch.fnmatch(norm, trimmed):
                return True
    return False


def _extract_file_path(data):
    ti = data.get("tool_input") or {}
    # Edit/Write both use "file_path"; be tolerant of a couple of aliases.
    return ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or ""


def build_output(message):
    """Allow-with-context PreToolUse JSON. Allows the edit, adds the reminder."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": message,
            "additionalContext": message,
        }
    }


def selftest():
    ok = True

    money = ["**/wallet/**", "**/ledger/**", "payout*", "*.balance.ts"]

    # 1. Matching paths.
    for p in [
        "src/wallet/payout.py",
        "app/ledger/entry.go",
        "payout_service.py",
        "core.balance.ts",
        "wallet/x.py",  # ** at root
    ]:
        if not path_matches(p, money):
            print("FAIL: should match: %s" % p); ok = False

    # 2. Non-matching paths => no-op.
    for p in ["src/ui/button.tsx", "README.md", "tests/test_math.py"]:
        if path_matches(p, money):
            print("FAIL: should NOT match: %s" % p); ok = False

    # 3. Empty money_paths => never matches (strict no-op default).
    if path_matches("src/wallet/payout.py", []):
        print("FAIL: empty money_paths should be a no-op"); ok = False

    # 4. Output allows (never blocks) and carries the checklist.
    out = build_output(DEFAULT_CHECKLIST)
    s = json.dumps(out)
    hso = json.loads(s)["hookSpecificOutput"]
    if hso.get("permissionDecision") != "allow":
        print("FAIL: decision must be allow"); ok = False
    if "deny" in s.lower():
        print("FAIL: payload must not deny"); ok = False
    if "ledger" not in hso.get("additionalContext", "").lower():
        print("FAIL: checklist text missing"); ok = False

    # 5. Windows-style backslash path matches.
    if not path_matches("src\\wallet\\payout.py", money):
        print("FAIL: backslash path should match"); ok = False

    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if sys.argv[1:] and sys.argv[1] == "--selftest":
        sys.exit(selftest())

    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        # Malformed payload: allow silently, never block.
        sys.exit(0)

    if data.get("tool_name") not in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        sys.exit(0)

    cfg = load_config()
    mi = cfg.get("money_inject", {})
    if not mi.get("enabled", True):
        sys.exit(0)

    money_globs = cfg.get("money_paths", []) or []
    if not money_globs:
        # Strict no-op by default.
        sys.exit(0)

    file_path = _extract_file_path(data)
    if path_matches(file_path, money_globs):
        message = mi.get("message") or DEFAULT_CHECKLIST
        sys.stdout.write(json.dumps(build_output(message)))
        sys.stdout.write("\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
