#!/usr/bin/env python3
"""Engram pre-commit scanner: secrets / PII / unshippable staged files.

Usage:
    python _scan.py --staged

For each staged file it blocks the commit if:
  (a) the file *path* matches a ``secret_scan.deny_paths`` glob, or
  (b) an *added* line matches a ``secret_scan.deny_patterns`` regex.

Pure Python 3 stdlib. Cross-platform. Exit 0 = clean, non-zero = blocked.
"""

import fnmatch
import re
import subprocess
import sys

from _common import BYPASS_COMMIT, eprint, load_config


def _staged_files():
    """Return list of staged file paths (added/copied/modified/renamed)."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p.strip()]


def _added_lines(path):
    """Return the text of lines *added* to ``path`` in the staged diff.

    We only scan added content so pre-existing history doesn't re-trigger, and
    we ignore the diff's ``+++`` header line.
    """
    out = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--", path],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if out.returncode != 0:
        return ""
    lines = []
    for line in out.stdout.splitlines():
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
    return "\n".join(lines)


def _path_matches(path, globs):
    """True if ``path`` (or its basename) matches any glob."""
    basename = path.rsplit("/", 1)[-1]
    for pattern in globs:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(basename, pattern):
            return True
    return False


def scan(config):
    """Return a list of (path, reason) offenders across staged files."""
    scan_cfg = config.get("secret_scan", {})
    deny_paths = scan_cfg.get("deny_paths", [])
    deny_patterns = scan_cfg.get("deny_patterns", [])

    compiled = []
    for pat in deny_patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error as exc:
            eprint("[engram] warning: bad deny_pattern %r skipped (%s)" % (pat, exc))

    offenders = []
    for path in _staged_files():
        if _path_matches(path, deny_paths):
            offenders.append((path, "path matches deny_paths glob"))
            # A denied path is unshippable regardless of content; move on.
            continue

        content = _added_lines(path)
        if not content:
            continue
        for raw_pat, rx in compiled:
            if rx.search(content):
                offenders.append(
                    (path, "added content matches pattern: %s" % raw_pat)
                )
                break  # one hit per file is enough to block
    return offenders


def main(argv):
    if "--staged" not in argv:
        eprint("usage: _scan.py --staged")
        return 2

    config = load_config()
    offenders = scan(config)
    if not offenders:
        return 0

    eprint("")
    eprint("[engram] pre-commit BLOCKED: possible secret / unshippable file staged")
    eprint("---------------------------------------------------------------")
    for path, reason in offenders:
        eprint("  x %s" % path)
        eprint("      %s" % reason)
    eprint("---------------------------------------------------------------")
    eprint("WHY: these files or lines look like credentials, keys, or private")
    eprint("     data that must never enter a public/shared history.")
    eprint("FIX: unstage the file (git restore --staged <file>), remove the")
    eprint("     secret, or add the path to your .gitignore.")
    eprint("BYPASS (emergency only): %s" % BYPASS_COMMIT)
    eprint("")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
