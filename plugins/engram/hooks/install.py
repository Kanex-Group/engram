#!/usr/bin/env python3
"""
Engram hooks installer
======================
Wires the two enforcement tiers into a target git repository:

  Tier 2 (git hooks)  — points the repo's `core.hooksPath` at the shipped
                        hooks/git/ directory, so pre-commit / commit-msg /
                        pre-push fire for ANY committer (human or tool).
  Tier 1 (Claude Code) — prints the settings snippet you paste into
                        .claude/settings.json so the harness enforces the
                        SessionStart + PreToolUse hooks.

Usage:
  python install.py [REPO]              install into REPO (default: cwd's repo)
  python install.py --uninstall [REPO]  revert core.hooksPath, restore any backup
  python install.py --print-snippet     just print the Claude Code snippet + where it goes
  python install.py --copy [REPO]       copy the git hooks in instead of using core.hooksPath
                                        (use when core.hooksPath is already taken)
  python install.py --check [REPO]      run brain_doctor health checks + report where the
                                        Claude Code hooks.json lives (verify, don't mutate)
  python install.py --selftest          dry-run install/check/uninstall in a temp repo

Idempotent. Pure stdlib. Cross-platform (Windows / macOS / Linux).
The git hooks are POSIX-sh wrappers; on Windows they run under the Git-for-Windows
bundled shell, so no extra setup is needed.
"""
import os, sys, json, shutil, subprocess

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))       # plugins/engram/hooks
PLUGIN_ROOT = os.path.dirname(HOOKS_DIR)                      # plugins/engram
GIT_HOOKS_SRC = os.path.join(HOOKS_DIR, "git")               # agent 1's dir
CLAUDE_DIR = os.path.join(HOOKS_DIR, "claude")               # agent 2's dir
SNIPPET = os.path.join(CLAUDE_DIR, "settings.snippet.json")
CC_HOOKS_JSON = os.path.join(HOOKS_DIR, "hooks.json")        # shipped CC hook definition
BRAIN_DOCTOR = os.path.join(PLUGIN_ROOT, "tools", "brain_doctor.py")
BACKUP_KEY = "engram.previoushookspath"                      # git config key remembering prior value


def _run(root, *a, check=True):
    r = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit("git %s failed: %s" % (" ".join(a), (r.stderr or r.stdout).strip()))
    return r.stdout.strip(), r.returncode


def _repo_root(start):
    r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Not inside a git repository: %s" % start)
    return r.stdout.strip()


def _current_hookspath(root):
    out, rc = _run(root, "config", "--local", "--get", "core.hooksPath", check=False)
    return out if rc == 0 and out else ""


def _print_snippet():
    print("\n--- Claude Code settings snippet -------------------------------------")
    if os.path.isfile(SNIPPET):
        with open(SNIPPET, encoding="utf-8") as f:
            print(f.read().rstrip())
    else:
        print("(settings.snippet.json not found — it ships in hooks/claude/. "
              "It wires SessionStart + PreToolUse hooks.)")
    print("--- end snippet ------------------------------------------------------")
    print("\nPaste the \"hooks\" block above into your repo's  .claude/settings.json")
    print("(create the file if it doesn't exist). If that file already has a")
    print("\"hooks\" key, merge the arrays rather than overwriting. The scripts")
    print("resolve via ${CLAUDE_PLUGIN_ROOT}; no absolute paths are baked in.\n")


def install(root, copy_mode=False):
    if not os.path.isdir(GIT_HOOKS_SRC):
        sys.exit("Shipped git hooks not found at %s (is the plugin intact?)" % GIT_HOOKS_SRC)

    if copy_mode:
        dest = os.path.join(root, ".git", "hooks")
        # resolve the real hooks dir (worktrees / submodules)
        common, rc = _run(root, "rev-parse", "--git-path", "hooks", check=False)
        if rc == 0 and common:
            dest = common if os.path.isabs(common) else os.path.join(root, common)
        os.makedirs(dest, exist_ok=True)
        copied = []
        for name in os.listdir(GIT_HOOKS_SRC):
            src = os.path.join(GIT_HOOKS_SRC, name)
            if not os.path.isfile(src):
                continue
            # only the three hook entrypoints are executable hooks; helpers (_*.py) go alongside
            dst = os.path.join(dest, name)
            shutil.copy2(src, dst)
            try:
                os.chmod(dst, 0o755)
            except OSError:
                pass
            copied.append(name)
        print("Copied %d hook file(s) into %s" % (len(copied), dest))
        print("Note: --copy does NOT auto-update if the plugin changes; re-run to refresh.")
    else:
        prev = _current_hookspath(root)
        if prev and os.path.abspath(prev) == os.path.abspath(GIT_HOOKS_SRC):
            print("Already installed: core.hooksPath -> %s" % GIT_HOOKS_SRC)
        else:
            if prev:
                # remember the prior value so --uninstall can restore it
                _run(root, "config", "--local", BACKUP_KEY, prev)
                print("Saved previous core.hooksPath (%s) under %s" % (prev, BACKUP_KEY))
            _run(root, "config", "--local", "core.hooksPath", GIT_HOOKS_SRC)
            print("Installed git hooks: core.hooksPath -> %s" % GIT_HOOKS_SRC)

    _print_snippet()
    print("Tier 2 (git hooks) is active now. Tier 1 (Claude Code) activates once you")
    print("paste the snippet above. Verify a hook fires:  git commit --allow-empty -m test")


def uninstall(root):
    prev, rc = _run(root, "config", "--local", "--get", BACKUP_KEY, check=False)
    cur = _current_hookspath(root)
    if cur and os.path.abspath(cur) == os.path.abspath(GIT_HOOKS_SRC):
        if rc == 0 and prev:
            _run(root, "config", "--local", "core.hooksPath", prev)
            _run(root, "config", "--local", "--unset", BACKUP_KEY, check=False)
            print("Restored previous core.hooksPath -> %s" % prev)
        else:
            _run(root, "config", "--local", "--unset", "core.hooksPath", check=False)
            print("Unset core.hooksPath (git falls back to .git/hooks).")
    else:
        # maybe backup lingered from a prior run; clean it up
        if rc == 0 and prev:
            _run(root, "config", "--local", "--unset", BACKUP_KEY, check=False)
        print("core.hooksPath was not pointing at Engram — nothing to revert.")
    print("\nRemove the Engram \"hooks\" block from .claude/settings.json manually to")
    print("disable Tier 1 (Claude Code) enforcement. If you used --copy, delete the")
    print("copied hook files from .git/hooks yourself.")


def _report_cc_hooks_location(root):
    """Tell the user exactly which file(s) carry the Claude Code hook wiring, so
    they can paste/verify. Reports the shipped definition and the project file
    the snippet gets merged into."""
    print("\n--- Claude Code hooks.json location ----------------------------------")
    if os.path.isfile(CC_HOOKS_JSON):
        print("shipped hook definition : %s" % CC_HOOKS_JSON)
    else:
        print("shipped hook definition : (hooks.json not found in %s)" % HOOKS_DIR)
    settings = os.path.join(root, ".claude", "settings.json")
    if os.path.isfile(settings):
        has_hooks = False
        try:
            with open(settings, encoding="utf-8") as f:
                has_hooks = "hooks" in (json.load(f) or {})
        except (OSError, ValueError):
            pass
        print("project settings        : %s  [%s]"
              % (settings, "hooks block present" if has_hooks
                 else "NO hooks block yet - paste the snippet"))
    else:
        print("project settings        : %s  [does not exist - create + paste snippet]"
              % settings)
    print("----------------------------------------------------------------------")


def check(root):
    """--check: verify wiring without mutating anything. Runs brain_doctor for
    the full health table, then points at the Claude Code hooks.json to verify.
    Returns brain_doctor's exit code (nonzero if any FAIL)."""
    rc = 0
    if os.path.isfile(BRAIN_DOCTOR):
        r = subprocess.run([sys.executable, BRAIN_DOCTOR, root])
        rc = r.returncode
    else:
        # graceful degrade: brain_doctor not shipped alongside — do the minimal
        # git-hooks check inline so --check still tells the user something useful.
        print("(brain_doctor.py not found at %s; running minimal check)" % BRAIN_DOCTOR)
        cur = _current_hookspath(root)
        if cur and os.path.abspath(cur) == os.path.abspath(GIT_HOOKS_SRC):
            print("  [PASS] git-hooks : core.hooksPath -> shipped hooks/git")
        else:
            print("  [FAIL] git-hooks : core.hooksPath not set to Engram - run install.py")
            rc = 1
    _report_cc_hooks_location(root)
    return rc


def _selftest():
    """Dry-run in a throwaway temp git repo: install -> check -> uninstall,
    asserting core.hooksPath is set, idempotent, and cleanly reverted. Never
    touches the caller's repo."""
    import tempfile
    failures = []

    def expect(cond, msg):
        (failures.append(msg) or print("  FAIL:", msg)) if not cond \
            else print("  ok  :", msg)

    tmp = tempfile.mkdtemp(prefix="engram_install_selftest_")
    try:
        subprocess.run(["git", "init", "-q", tmp], capture_output=True, text=True)
        root = _repo_root(tmp)

        # pre-seed a prior hooksPath so we can prove backup/restore
        _run(root, "config", "--local", "core.hooksPath", ".githooks-prior")

        install(root)  # default: core.hooksPath mode
        expect(os.path.abspath(_current_hookspath(root)) ==
               os.path.abspath(GIT_HOOKS_SRC),
               "install sets core.hooksPath -> shipped hooks/git")
        prev, rc = _run(root, "config", "--local", "--get", BACKUP_KEY, check=False)
        expect(rc == 0 and prev == ".githooks-prior",
               "prior core.hooksPath backed up under %s" % BACKUP_KEY)

        # idempotency: second install must not corrupt or lose the backup
        install(root)
        expect(os.path.abspath(_current_hookspath(root)) ==
               os.path.abspath(GIT_HOOKS_SRC),
               "second install idempotent (hooksPath unchanged)")

        # --check runs and returns brain_doctor's code (nonzero: repo not fully
        # wired) without raising
        crc = check(root)
        expect(isinstance(crc, int), "--check returns an int exit code (%r)" % crc)

        uninstall(root)
        expect(_current_hookspath(root) == ".githooks-prior",
               "uninstall restores the prior core.hooksPath")
        _, rc2 = _run(root, "config", "--local", "--get", BACKUP_KEY, check=False)
        expect(rc2 != 0, "backup key cleared after uninstall")

        # copy-mode dry run into a second temp repo
        tmp2 = tempfile.mkdtemp(prefix="engram_install_copy_")
        subprocess.run(["git", "init", "-q", tmp2], capture_output=True, text=True)
        root2 = _repo_root(tmp2)
        install(root2, copy_mode=True)
        hooks_dir, _ = _run(root2, "rev-parse", "--git-path", "hooks", check=False)
        hooks_dir = hooks_dir if os.path.isabs(hooks_dir) \
            else os.path.join(root2, hooks_dir)
        expect(all(os.path.isfile(os.path.join(hooks_dir, e))
                   for e in ("pre-commit", "commit-msg", "pre-push")),
               "copy-mode drops the 3 hook entrypoints into .git/hooks")
        shutil.rmtree(tmp2, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 50)
    if failures:
        print("SELFTEST FAILED: %d assertion(s)" % len(failures))
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    if "--print-snippet" in argv:
        _print_snippet()
        return 0
    do_uninstall = "--uninstall" in argv
    do_check = "--check" in argv
    copy_mode = "--copy" in argv
    positional = [a for a in argv if not a.startswith("-")]
    start = positional[0] if positional else os.getcwd()
    root = _repo_root(start)
    if do_check:
        return check(root)
    if do_uninstall:
        uninstall(root)
    else:
        install(root, copy_mode=copy_mode)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
