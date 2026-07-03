#!/usr/bin/env python3
"""Engram commit-msg hook: block AI-authorship fingerprint trailers.

Usage:
    python _fingerprint.py <commit-msg-file>

If any line of the commit message matches a ``fingerprint.deny_trailers``
regex (e.g. ``Co-Authored-By: Claude``), print the offending line and exit
non-zero.

Rationale: an AI-authorship trailer once broke a real auto-deploy pipeline,
so these trailers must never enter the commit history.

Pure Python 3 stdlib. Cross-platform.
"""

import re
import sys

from _common import BYPASS_COMMIT, eprint, load_config


def find_offenders(message, deny_trailers):
    """Return list of (lineno, line, pattern) matches in the message."""
    compiled = []
    for pat in deny_trailers:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error as exc:
            eprint("[engram] warning: bad deny_trailer %r skipped (%s)" % (pat, exc))

    offenders = []
    for idx, line in enumerate(message.splitlines(), start=1):
        # Skip comment lines git strips from the final message.
        if line.lstrip().startswith("#"):
            continue
        for raw_pat, rx in compiled:
            if rx.search(line):
                offenders.append((idx, line.rstrip(), raw_pat))
                break
    return offenders


def main(argv):
    if not argv:
        eprint("usage: _fingerprint.py <commit-msg-file>")
        return 2

    msg_path = argv[0]
    try:
        with open(msg_path, "r", encoding="utf-8", errors="replace") as fh:
            message = fh.read()
    except OSError as exc:
        eprint("[engram] warning: could not read commit message (%s); allowing" % exc)
        return 0

    config = load_config()
    deny_trailers = config.get("fingerprint", {}).get("deny_trailers", [])
    offenders = find_offenders(message, deny_trailers)
    if not offenders:
        return 0

    eprint("")
    eprint("[engram] commit-msg BLOCKED: AI-authorship fingerprint in message")
    eprint("---------------------------------------------------------------")
    for lineno, line, pat in offenders:
        eprint("  line %d: %s" % (lineno, line))
        eprint("           matched: %s" % pat)
    eprint("---------------------------------------------------------------")
    eprint("WHY: AI-authorship trailers (Co-Authored-By / 'Generated with')")
    eprint("     must not enter commit history -- one such trailer previously")
    eprint("     broke a real auto-deploy pipeline.")
    eprint("FIX: remove the offending line(s) from your commit message.")
    eprint("BYPASS (emergency only): %s" % BYPASS_COMMIT)
    eprint("")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
