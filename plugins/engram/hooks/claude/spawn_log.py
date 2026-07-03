#!/usr/bin/env python3
"""Engram Claude Code hook: PostToolUse(Task|Agent) sub-agent spawn logger.

Records every sub-agent spawn (Task / Agent tool call) to an append-only JSONL
log so you can later see how much work a session fanned out. NON-BLOCKING: this
hook only observes; it always exits 0 and never emits a permission decision.

  stdin  : JSON PostToolUse payload, e.g.
             {"hook_event_name":"PostToolUse","tool_name":"Task",
              "tool_input":{...},"tool_response":{...},"cwd":"/repo", ...}
  effect : appends one JSON line to the configured spawn log (default
             ``.engram/spawn-log.jsonl`` under cwd):
             {"ts": <monotonic-ish counter or null>, "tool": "Task",
              "outcome": "ok"}
  stdout : nothing (PostToolUse has no decision to make here).
  exit   : 0 always.

Companion tally: ``python spawn_log.py --tally [path]`` prints spawn counts by
tool from the log (default log path). ``--selftest`` runs built-in fixtures.

Config (engram.hooks.json, optional; built-in defaults if absent/broken):
  "spawn_log": {
     "enabled": true,
     "path": ".engram/spawn-log.jsonl",
     "tools": ["Task", "Agent"]
  }

The timestamp is intentionally NOT a wall-clock call: we keep a tiny monotonic
counter persisted next to the log so ordering is preserved without depending on
anything unavailable or non-deterministic. Set "ts" to null to omit it.

Pure Python 3 stdlib. Cross-platform. No project/personal data.
"""
import json
import os
import sys


DEFAULTS = {
    "spawn_log": {
        "enabled": True,
        "path": os.path.join(".engram", "spawn-log.jsonl"),
        # Which tool_name values count as a sub-agent spawn.
        "tools": ["Task", "Agent"],
        # If false, "ts" is written as null instead of a monotonic counter.
        "counter_ts": True,
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
    """Load engram.hooks.json from the parent of this script's dir, else defaults."""
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


def _log_path(cfg, cwd):
    path = cfg.get("spawn_log", {}).get("path") or os.path.join(
        ".engram", "spawn-log.jsonl"
    )
    if not os.path.isabs(path):
        path = os.path.join(cwd or ".", path)
    return os.path.normpath(path)


def _next_counter(log_path):
    """Return a monotonic-ish counter persisted beside the log.

    Uses a small sidecar file (<log>.seq). Best-effort: on any error, returns 0.
    This avoids depending on a wall clock while still ordering entries.
    """
    seq_path = log_path + ".seq"
    val = 0
    try:
        if os.path.isfile(seq_path):
            with open(seq_path, "r", encoding="utf-8") as fh:
                val = int((fh.read() or "0").strip() or "0")
    except Exception:
        val = 0
    val += 1
    try:
        with open(seq_path, "w", encoding="utf-8") as fh:
            fh.write(str(val))
    except Exception:
        pass
    return val


def _classify_outcome(data):
    """Best-effort ok/error classification from the PostToolUse payload."""
    resp = data.get("tool_response")
    if isinstance(resp, dict):
        # Common shapes: {"is_error": true} or {"error": "..."}.
        if resp.get("is_error") or resp.get("error"):
            return "error"
    if isinstance(resp, str) and resp.lower().startswith("error"):
        return "error"
    return "ok"


def append_entry(cfg, cwd, tool, outcome):
    """Append one JSONL record. Returns the entry dict (also for --selftest)."""
    log_path = _log_path(cfg, cwd)
    parent = os.path.dirname(log_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
    use_counter = cfg.get("spawn_log", {}).get("counter_ts", True)
    ts = _next_counter(log_path) if use_counter else None
    entry = {"ts": ts, "tool": tool, "outcome": outcome}
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry))
            fh.write("\n")
    except Exception:
        # Logging must never break the session; swallow write errors.
        pass
    return entry


def tally(log_path):
    """Print counts by tool (and outcome) from the given JSONL log."""
    counts = {}
    outcomes = {}
    total = 0
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                tool = rec.get("tool", "?")
                oc = rec.get("outcome", "?")
                counts[tool] = counts.get(tool, 0) + 1
                outcomes[oc] = outcomes.get(oc, 0) + 1
                total += 1
    except FileNotFoundError:
        sys.stdout.write("spawn-log: no log at {p} (0 spawns)\n".format(p=log_path))
        return 0
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write("spawn-log: could not read {p}: {e}\n".format(p=log_path, e=exc))
        return 1

    sys.stdout.write("spawn-log tally ({p}) -- {t} spawn(s)\n".format(p=log_path, t=total))
    for tool in sorted(counts):
        sys.stdout.write("  {tool}: {n}\n".format(tool=tool, n=counts[tool]))
    if outcomes:
        parts = ", ".join("{k}={v}".format(k=k, v=outcomes[k]) for k in sorted(outcomes))
        sys.stdout.write("  outcomes: {parts}\n".format(parts=parts))
    return 0


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def selftest():
    import tempfile

    ok = True
    tmp = tempfile.mkdtemp(prefix="engram_spawnlog_")
    cfg = _deep_merge(DEFAULTS, {"spawn_log": {"path": "sub/spawn-log.jsonl"}})

    # 1. Appends an entry for a matching tool, creating the dir.
    e1 = append_entry(cfg, tmp, "Task", "ok")
    log_path = _log_path(cfg, tmp)
    if not os.path.isfile(log_path):
        print("FAIL: log file not created"); ok = False
    if e1["tool"] != "Task" or e1["outcome"] != "ok":
        print("FAIL: entry fields wrong: %r" % e1); ok = False

    # 2. Monotonic counter increments across appends.
    e2 = append_entry(cfg, tmp, "Agent", "error")
    if not (isinstance(e1["ts"], int) and isinstance(e2["ts"], int) and e2["ts"] > e1["ts"]):
        print("FAIL: counter not monotonic: %r -> %r" % (e1["ts"], e2["ts"])); ok = False

    # 3. JSONL is valid and has 2 lines.
    with open(log_path, "r", encoding="utf-8") as fh:
        lines = [l for l in fh.read().splitlines() if l.strip()]
    if len(lines) != 2:
        print("FAIL: expected 2 lines, got %d" % len(lines)); ok = False
    for l in lines:
        json.loads(l)  # raises if invalid

    # 4. Tally counts by tool.
    rc = tally(log_path)
    if rc != 0:
        print("FAIL: tally returned %d" % rc); ok = False

    # 5. counter_ts=false yields null ts.
    cfg2 = _deep_merge(DEFAULTS, {"spawn_log": {"path": "b/log.jsonl", "counter_ts": False}})
    e3 = append_entry(cfg2, tmp, "Task", "ok")
    if e3["ts"] is not None:
        print("FAIL: counter_ts=false should give null ts, got %r" % e3["ts"]); ok = False

    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--selftest":
        sys.exit(selftest())
    if argv and argv[0] == "--tally":
        cfg = load_config()
        path = argv[1] if len(argv) > 1 else _log_path(cfg, os.getcwd())
        sys.exit(tally(path))

    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        # Malformed payload: do nothing, never block.
        sys.exit(0)

    cfg = load_config()
    if not cfg.get("spawn_log", {}).get("enabled", True):
        sys.exit(0)

    tool = data.get("tool_name")
    watched = cfg.get("spawn_log", {}).get("tools", ["Task", "Agent"])
    if tool in watched:
        cwd = data.get("cwd") or os.getcwd()
        append_entry(cfg, cwd, tool, _classify_outcome(data))

    # PostToolUse observer: no stdout decision, always exit 0.
    sys.exit(0)


if __name__ == "__main__":
    main()
