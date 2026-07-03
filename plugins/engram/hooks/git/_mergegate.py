#!/usr/bin/env python3
"""Engram pre-push hook: gate pushes to protected branches on a QA record.

Usage (git pre-push protocol):
    python _mergegate.py <remote-name> <remote-url>
    ... with ref lines on stdin, one per pushed ref:
        <local ref> <local sha> <remote ref> <remote sha>

If any pushed ref targets a protected branch (config ``protected_branches``),
require a *complete* QA record: a file matching ``qa.record_glob`` under
``qa.dir`` (searched from the repo root) whose text contains ``qa.passed_marker``.
If none exists, block the push and point at the pre-merge-check flow.

Pure Python 3 stdlib. Cross-platform.
"""

import glob
import os
import subprocess
import sys

from _common import BYPASS_PUSH, eprint, load_config, repo_root

# git uses this sentinel sha (all zeros) for a deleted ref.
_ZERO = "0" * 40
_ZERO64 = "0" * 64


def _branch_from_ref(ref):
    """Extract a branch name from a full ref like refs/heads/main."""
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/"):]
    return ref


def parse_push_refs(stdin_text):
    """Parse git pre-push stdin into a list of remote branch names being pushed.

    Deletions (local sha all-zero) are skipped -- deleting a branch is not a
    content push and should not require a QA record.
    """
    branches = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, _remote_sha = parts
        if local_sha in (_ZERO, _ZERO64):
            continue  # branch deletion
        branches.append(_branch_from_ref(remote_ref))
    return branches


def _qa_check_tool():
    """Path to the shared tools/qa_check.py completeness checker, or None.

    Lives at ``<plugin_root>/tools/qa_check.py`` -- two levels up from this
    hooks/git/ dir. Built by a sibling agent; may be absent in older installs.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(
        os.path.join(here, "..", "..", "tools", "qa_check.py")
    )
    return candidate if os.path.isfile(candidate) else None


def _qa_record_paths(config, root):
    """Yield candidate QA record file paths under the configured QA dir."""
    qa = config.get("qa", {})
    qa_dir = qa.get("dir", "QA")
    record_glob = qa.get("record_glob", "QA_*.md")

    search_dir = os.path.join(root, qa_dir)
    if not os.path.isdir(search_dir):
        return []

    patterns = [
        os.path.join(search_dir, record_glob),
        os.path.join(search_dir, "**", record_glob),
    ]
    seen = []
    seen_set = set()
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            if path in seen_set or not os.path.isfile(path):
                continue
            seen_set.add(path)
            seen.append(path)
    return seen


def _record_complete_by_grep(path, passed_marker):
    """Legacy fallback: record is 'complete' if it contains the passed_marker."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return passed_marker in fh.read()
    except OSError:
        return False


def find_passed_qa_record(config, root):
    """Return the path of a COMPLETE QA record, or None.

    Completeness is decided by the shared ``tools/qa_check.py`` (exit 0 == the
    record is complete: status PASSED *and* no unticked applicable checkboxes).
    If that tool is not shipped, fall back to the historical exists+marker grep
    so this hook still gates standalone.
    """
    qa = config.get("qa", {})
    passed_marker = qa.get("passed_marker", "status: PASSED")
    paths = _qa_record_paths(config, root)
    tool = _qa_check_tool()

    for path in paths:
        if tool is not None:
            try:
                proc = subprocess.run(
                    [sys.executable, tool, path],
                    capture_output=True,
                    text=True,
                    cwd=root,
                    check=False,
                )
                if proc.returncode == 0:
                    return path
                # qa_check ran and judged this record INCOMPLETE -> do not accept
                # it via grep; move to the next candidate.
                continue
            except OSError:
                # Tool present but couldn't be launched: fall back to grep.
                pass
        if _record_complete_by_grep(path, passed_marker):
            return path
    return None


def main(argv):
    config = load_config()
    protected = set(config.get("protected_branches", []))

    stdin_text = ""
    if not sys.stdin.isatty():
        try:
            stdin_text = sys.stdin.read()
        except (OSError, ValueError):
            stdin_text = ""

    pushed = parse_push_refs(stdin_text)
    targeted = [b for b in pushed if b in protected]
    if not targeted:
        return 0  # nothing protected being pushed

    root = repo_root()
    if root is None:
        # Can't locate the repo -> can't verify QA. Fail safe: block.
        eprint("[engram] pre-push BLOCKED: cannot locate git repo root to verify QA.")
        eprint("BYPASS (emergency only): %s" % BYPASS_PUSH)
        return 1

    record = find_passed_qa_record(config, root)
    if record is not None:
        return 0  # protected push allowed -- QA on record

    qa = config.get("qa", {})
    eprint("")
    eprint("[engram] pre-push BLOCKED: protected branch push without a COMPLETE QA record")
    eprint("---------------------------------------------------------------")
    eprint("  protected branch(es) targeted: %s" % ", ".join(sorted(set(targeted))))
    eprint("  looked for: %s/%s that passes qa_check (complete)"
           % (qa.get("dir", "QA"), qa.get("record_glob", "QA_*.md")))
    eprint("  completeness = status PASSED AND no unticked applicable checkboxes")
    eprint("---------------------------------------------------------------")
    eprint("WHY: pushes to a protected branch must be backed by a COMPLETE QA")
    eprint("     record. None found (a record may exist but still be incomplete).")
    eprint("FIX: run your pre-merge-check flow, tick every applicable box, set")
    eprint("     status: PASSED, then push again.")
    eprint("BYPASS (emergency only): %s" % BYPASS_PUSH)
    eprint("")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
