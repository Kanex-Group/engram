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

Idempotent. Pure stdlib. Cross-platform (Windows / macOS / Linux).
The git hooks are POSIX-sh wrappers; on Windows they run under the Git-for-Windows
bundled shell, so no extra setup is needed.
"""
import os, sys, json, shutil, subprocess

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))       # plugins/engram/hooks
GIT_HOOKS_SRC = os.path.join(HOOKS_DIR, "git")               # agent 1's dir
CLAUDE_DIR = os.path.join(HOOKS_DIR, "claude")               # agent 2's dir
SNIPPET = os.path.join(CLAUDE_DIR, "settings.snippet.json")
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


def main(argv):
    if "--print-snippet" in argv:
        _print_snippet()
        return
    do_uninstall = "--uninstall" in argv
    copy_mode = "--copy" in argv
    positional = [a for a in argv if not a.startswith("-")]
    start = positional[0] if positional else os.getcwd()
    root = _repo_root(start)
    if do_uninstall:
        uninstall(root)
    else:
        install(root, copy_mode=copy_mode)


if __name__ == "__main__":
    main(sys.argv[1:])
