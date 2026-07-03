#!/usr/bin/env python3
"""Engram Claude Code hook: Stop verification nudge (NON-BLOCKING).

When the agent is about to finish its turn, emit a gentle reminder asking whether
it actually verified its work (ran a test, took a screenshot, checked a log)
before claiming "done". This is a NUDGE ONLY -- it never hard-blocks the stop.

  stdin  : JSON Stop payload, e.g.
             {"hook_event_name":"Stop","stop_hook_active":false,"cwd":"/repo", ...}
  stdout : valid Stop-hook JSON carrying additionalContext (the reminder). We do
           NOT set "decision":"block", so the stop proceeds normally (fail-open).
             {"hookSpecificOutput": {"hookEventName": "Stop",
                                     "additionalContext": "<reminder>"}}
  exit   : 0 always.

FAIL-OPEN by construction: any error, disabled config, or already-active stop
loop results in a clean exit 0 with no block. There is no code path that blocks.

Config (engram.hooks.json, optional; built-in defaults if absent/broken):
  "stop_verify": {
     "enabled": true,
     "message": "<override reminder text>"   # optional
  }

Set "enabled": false to silence the nudge entirely.

Pure Python 3 stdlib. Cross-platform. No project/personal data.
"""
import json
import os
import sys


DEFAULT_MESSAGE = (
    "Engram nudge (reminder only, not a block): before claiming this is done, "
    "did you VERIFY it? Run the test, take the screenshot, or check the log that "
    "proves the change works -- don't assert 'done' from reading the code alone. "
    "If you already verified, ignore this and stop."
)

DEFAULTS = {
    "stop_verify": {
        "enabled": True,
        "message": DEFAULT_MESSAGE,
    }
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


def build_output(message):
    """Non-blocking Stop-hook JSON: additionalContext only, no block decision."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }


def selftest():
    ok = True

    # 1. Output is valid JSON, carries the message, and does NOT block.
    out = build_output(DEFAULT_MESSAGE)
    serialized = json.dumps(out)
    reparsed = json.loads(serialized)
    hso = reparsed.get("hookSpecificOutput", {})
    if hso.get("hookEventName") != "Stop":
        print("FAIL: wrong hookEventName"); ok = False
    if "verify" not in hso.get("additionalContext", "").lower():
        print("FAIL: reminder text missing"); ok = False
    # Critical: never a block DECISION in the payload (the reminder prose may
    # contain the word "block"; we assert on the structural decision fields).
    if reparsed.get("decision") == "block":
        print("FAIL: decision=block present"); ok = False
    if hso.get("permissionDecision") == "deny":
        print("FAIL: permissionDecision=deny present"); ok = False
    if reparsed.get("continue") is False:
        print("FAIL: continue=false would halt the agent"); ok = False

    # 2. Config override message flows through.
    cfg = _deep_merge(DEFAULTS, {"stop_verify": {"message": "custom nudge"}})
    if cfg["stop_verify"]["message"] != "custom nudge":
        print("FAIL: config override not applied"); ok = False

    # 3. Disabled config path yields no output (simulated).
    cfg_off = _deep_merge(DEFAULTS, {"stop_verify": {"enabled": False}})
    if cfg_off["stop_verify"]["enabled"] is not False:
        print("FAIL: disable flag not honored"); ok = False

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
        # Malformed payload: fail open, no nudge, no block.
        sys.exit(0)

    # If we're already inside a stop-hook continuation loop, stay silent so we
    # never nag repeatedly (still non-blocking either way).
    if data.get("stop_hook_active"):
        sys.exit(0)

    cfg = load_config()
    sv = cfg.get("stop_verify", {})
    if not sv.get("enabled", True):
        sys.exit(0)

    message = sv.get("message") or DEFAULT_MESSAGE
    sys.stdout.write(json.dumps(build_output(message)))
    sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
