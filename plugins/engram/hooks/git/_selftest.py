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


def case_db_file_blocked(root):
    """A staged *.db file is blocked by the extended path denylist."""
    _write(root, "data.db", "SQLite format 3\x00 (binary-ish)\n")
    _git(["add", "data.db"], root)
    rc, out, err = _git(["commit", "-m", "add db"], root)
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("staged *.db file is blocked", blocked, out + err)
    _git(["reset", "-q"], root)
    try:
        os.remove(os.path.join(root, "data.db"))
    except OSError:
        pass


def case_obsidian_file_blocked(root):
    """A staged file under .obsidian/ is blocked (vault internals)."""
    _write(root, os.path.join(".obsidian", "workspace.json"), "{}\n")
    _git(["add", os.path.join(".obsidian", "workspace.json")], root)
    rc, out, err = _git(["commit", "-m", "add vault config"], root)
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("staged .obsidian/ file is blocked", blocked, out + err)
    _git(["reset", "-q"], root)
    try:
        os.remove(os.path.join(root, ".obsidian", "workspace.json"))
    except OSError:
        pass


def case_configured_vault_dir_blocked(root):
    """Unit-test the vault_dirs -> deny logic in _scan directly.

    (A live commit test can't reliably inject config here because _common's
    load_config finds the shipped hooks/engram.hooks.json before any repo-root
    file. The new logic itself -- vault_dirs expands to a directory denylist and
    _path_matches honours the directory shorthand -- is what we assert.)
    """
    sys.path.insert(0, HOOK_DIR)
    import importlib

    _scan = importlib.import_module("_scan")
    cfg = {"vault_dirs": ["private_vault"], "deny_paths": []}
    globs = _scan._effective_deny_paths(cfg)
    hit_inside = _scan._path_matches("private_vault/note.md", globs)
    hit_nested = _scan._path_matches("sub/private_vault/deep/n.md", globs)
    miss_other = _scan._path_matches("src/main.py", globs)
    # Also confirm the always-on DB/vault-internal globs match.
    hit_db = _scan._path_matches("data.db", globs)
    hit_obs = _scan._path_matches(".obsidian/workspace.json", globs)
    passed = hit_inside and hit_nested and (not miss_other) and hit_db and hit_obs
    detail = "inside=%s nested=%s other=%s db=%s obs=%s" % (
        hit_inside, hit_nested, miss_other, hit_db, hit_obs)
    _record("configured vault_dir + extra file globs deny correctly", passed, detail)


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


def case_incomplete_qa_record_blocked(root):
    """A QA record present but WITHOUT the passed marker must NOT satisfy the gate.

    Covers the completeness check (grep fallback): a record that merely EXISTS is
    not enough; it must be complete. We add an incomplete record on its own
    branch state and confirm the push is still blocked.
    """
    _write(root, os.path.join("QA", "QA_9000.md"),
           "# QA record\n\nstatus: IN_PROGRESS\n- [ ] tests pass\n")
    _git(["add", os.path.join("QA", "QA_9000.md")], root)
    _git(["commit", "-m", "Add incomplete QA record"], root)

    sha = _head_sha(root)
    stdin = _push_stdin(sha, "main")
    rc, out, err = _run(
        [sys.executable, os.path.join(HOOK_DIR, "_mergegate.py"), "origin",
         "https://example.invalid/repo.git"],
        cwd=root,
        stdin=stdin,
    )
    blocked = rc != 0 and "engram" in (out + err).lower()
    _record("push blocked when only an INCOMPLETE QA record exists", blocked, out + err)
    # Remove the incomplete record so the later complete-record case is clean.
    try:
        os.remove(os.path.join(root, "QA", "QA_9000.md"))
    except OSError:
        pass
    _git(["add", "-A"], root)
    _git(["commit", "-m", "remove incomplete QA record"], root)


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
        case_db_file_blocked(tmp)
        case_obsidian_file_blocked(tmp)
        case_configured_vault_dir_blocked(tmp)
        case_fingerprint_msg_blocked(tmp)
        clean_ok = case_clean_commit_passes(tmp)
        # The push cases need at least one commit on HEAD.
        if not clean_ok:
            # Force a commit so push cases still have a HEAD sha to work with.
            _write(tmp, "seed.txt", "seed\n")
            _git(["add", "seed.txt"], tmp)
            _git(["commit", "-m", "seed", "--no-verify"], tmp)
        case_push_to_main_without_qa_blocked(tmp)
        case_incomplete_qa_record_blocked(tmp)
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
