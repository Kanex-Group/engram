#!/usr/bin/env python3
"""Self-test for the Engram Tier 2 git hooks.

Spins up a throwaway git repo, points ``core.hooksPath`` at this ``git/`` dir,
and asserts the four behavior contracts:

  1. a commit staging a secret is BLOCKED (pre-commit / _scan.py)
  2. a commit whose message carries a fingerprint trailer is BLOCKED (commit-msg)
  3. a push to a protected branch WITHOUT a QA record is BLOCKED (pre-push)
  4. a clean commit + a push WITH a passing QA record both PASS

Prints PASS/FAIL per case and exits non-zero if any case fails.

Pure Python 3 stdlib. Cross-platform (Windows git-bash, macOS, Linux).
"""

import os
import shutil
import subprocess
import sys
import tempfile

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))

# Track results across cases.
_RESULTS = []


def _run(cmd, cwd, env=None, stdin=None):
    """Run a command, returning (returncode, stdout, stderr)."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        input=stdin,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _git(args, cwd, stdin=None):
    return _run(["git"] + args, cwd, stdin=stdin)


def _record(name, passed, detail=""):
    _RESULTS.append((name, passed))
    status = "PASS" if passed else "FAIL"
    line = "[%s] %s" % (status, name)
    if detail and not passed:
        line += "\n        %s" % detail.strip().replace("\n", "\n        ")
    print(line)


def _init_repo(root):
    _git(["init", "-q"], root)
    _git(["config", "user.email", "tester@example.invalid"], root)
    _git(["config", "user.name", "Engram Selftest"], root)
    # Point git at the shipped hook dir. This is the whole enforcement wiring.
    _git(["config", "core.hooksPath", HOOK_DIR], root)
    # Ensure a deterministic default branch name for the QA/push cases.
    _git(["checkout", "-q", "-b", "work"], root)


def _write(root, rel, text):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def case_secret_commit_blocked(root):
    _write(root, "leak.txt", "api_key = 'SUPERSECRETVALUE123'\n")
    _git(["add", "leak.txt"], root)
    rc, out, err = _git(["commit", "-m", "add config"], root)
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("secret commit is blocked", blocked, out + err)
    # Clean up staging for later cases.
    _git(["reset", "-q"], root)
    try:
        os.remove(os.path.join(root, "leak.txt"))
    except OSError:
        pass


def case_fingerprint_msg_blocked(root):
    _write(root, "ok.txt", "harmless content\n")
    _git(["add", "ok.txt"], root)
    msg = "Real change\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    rc, out, err = _git(["commit", "-m", msg], root)
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("fingerprint commit message is blocked", blocked, out + err)
    _git(["reset", "-q"], root)


def case_clean_commit_passes(root):
    # ok.txt is still staged-able; re-add and commit with a clean message.
    _git(["add", "ok.txt"], root)
    rc, out, err = _git(["commit", "-m", "Add harmless file"], root)
    passed = rc == 0
    _record("clean commit passes", passed, out + err)
    return passed


def _push_stdin(local_sha, remote_branch):
    # git pre-push protocol line: <local ref> <local sha> <remote ref> <remote sha>
    return "refs/heads/%s %s refs/heads/%s %s\n" % (
        remote_branch,
        local_sha,
        remote_branch,
        "0" * 40,
    )


def _head_sha(root):
    rc, out, _err = _git(["rev-parse", "HEAD"], root)
    return out.strip() if rc == 0 else "0" * 40


def case_push_to_main_without_qa_blocked(root):
    """Invoke the pre-push hook the way git does: argv + stdin refs."""
    sha = _head_sha(root)
    stdin = _push_stdin(sha, "main")
    rc, out, err = _run(
        [sys.executable, os.path.join(HOOK_DIR, "_mergegate.py"), "origin",
         "https://example.invalid/repo.git"],
        cwd=root,
        stdin=stdin,
    )
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("push to protected branch without QA is blocked", blocked, out + err)


def case_push_to_main_with_qa_passes(root):
    """Add a passing QA record, then the same pre-push invocation should pass."""
    _write(root, os.path.join("QA", "QA_0001.md"),
           "# QA record\n\nstatus: PASSED\n")
    _git(["add", os.path.join("QA", "QA_0001.md")], root)
    _git(["commit", "-m", "Add QA record"], root)

    sha = _head_sha(root)
    stdin = _push_stdin(sha, "main")
    rc, out, err = _run(
        [sys.executable, os.path.join(HOOK_DIR, "_mergegate.py"), "origin",
         "https://example.invalid/repo.git"],
        cwd=root,
        stdin=stdin,
    )
    passed = rc == 0
    _record("push to protected branch WITH QA record passes", passed, out + err)


def case_non_protected_push_passes(root):
    """A push to a non-protected branch needs no QA record."""
    sha = _head_sha(root)
    stdin = _push_stdin(sha, "feature-x")
    rc, out, err = _run(
        [sys.executable, os.path.join(HOOK_DIR, "_mergegate.py"), "origin",
         "https://example.invalid/repo.git"],
        cwd=root,
        stdin=stdin,
    )
    passed = rc == 0
    _record("push to non-protected branch passes", passed, out + err)


def main():
    # Guard: git must be available.
    if shutil.which("git") is None:
        print("[FAIL] git not found on PATH; cannot run self-test")
        return 2

    tmp = tempfile.mkdtemp(prefix="engram_hook_selftest_")
    try:
        _init_repo(tmp)
        case_secret_commit_blocked(tmp)
        case_fingerprint_msg_blocked(tmp)
        clean_ok = case_clean_commit_passes(tmp)
        # The push cases need at least one commit on HEAD.
        if not clean_ok:
            # Force a commit so push cases still have a HEAD sha to work with.
            _write(tmp, "seed.txt", "seed\n")
            _git(["add", "seed.txt"], tmp)
            _git(["commit", "-m", "seed", "--no-verify"], tmp)
        case_push_to_main_without_qa_blocked(tmp)
        case_non_protected_push_passes(tmp)
        case_push_to_main_with_qa_passes(tmp)
    finally:
        # Windows can hold locks on .git objects briefly; retry rmtree.
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(_RESULTS)
    failed = [n for n, ok in _RESULTS if not ok]
    print("")
    print("-------------------------------------------------------")
    print("Engram git-hook self-test: %d/%d passed"
          % (total - len(failed), total))
    if failed:
        print("FAILED cases:")
        for name in failed:
            print("  - %s" % name)
        return 1
    print("ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
