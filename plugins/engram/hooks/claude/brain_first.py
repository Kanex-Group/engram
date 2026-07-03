#!/usr/bin/env python3
"""Engram Tier-1 Claude Code hook: SessionStart brain-first orientation.

Prints a concise "consult the knowledge vault first" orientation block so that
orienting from the shared brain is harness-guaranteed at every session start,
not left to the agent's discretion.

I/O contract (Claude Code SessionStart hook):
  stdin  : JSON with fields like {"hook_event_name":"SessionStart","source":"startup",...}
           (we do not require any of it, but we read/ignore it so the pipe drains cleanly)
  stdout : a JSON object of the form
             {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                     "additionalContext": "<text>"}}
           The `additionalContext` string is injected into the agent's context.
           We also print the same text to stderr-free stdout-compatible form; the
           JSON object is the authoritative, documented channel.
  exit   : 0 (success)

Pure Python 3 stdlib. Cross-platform. No project/personal data.
"""
import json
import sys

ORIENTATION = """\
[Engram - brain-first orientation]
The knowledge vault (OBrain) is the source of truth for this project, not your
own prior context. Before acting:
  1. READ FIRST. Open the vault index, then follow ONE linked note relevant to
     the task. Do not build from memory when the vault can tell you.
  2. CONSULT BEFORE YOU ACT. Check the brain for prior decisions, conventions,
     and open issues before writing code or making structural edits.
  3. KEEP CONTEXT LEAN. Pull only what the task needs; route heavy or multi-part
     work to sub-agents instead of loading everything into this context.
  4. WRITE IT DOWN. Log decisions, issues, and fixes back to the vault in the
     same session so the brain stays current and the next session inherits it.
Enforcement note: git pushes to protected branches, AI-authorship commit
trailers, and staging of secret files are blocked by Engram hooks."""


def main():
    # Drain stdin if present so the writer side never blocks; content is optional.
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except Exception:
        pass

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ORIENTATION,
        }
    }
    # Authoritative documented channel: JSON with additionalContext.
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
