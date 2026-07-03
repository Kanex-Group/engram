#!/usr/bin/env python3
"""Changelog check — plugin content changed but CHANGELOG.md didn't.

If a change touches shipped plugin content but forgets to add a CHANGELOG entry,
downstream consumers can't tell what moved. This tool inspects the changed files
in a repo and WARNS (non-zero) when plugin content changed but CHANGELOG.md is
NOT among the changed files.

Advisory: it flags the omission; it does not block.

Usage:
  python changelog_check.py <repo>

  <repo>   path inside the git repo to check.

By default it looks at the union of staged and unstaged changes (what a commit
would carry). Use --staged to consider only staged files.

Exit 0 when OK (no plugin content changed, or CHANGELOG.md is in the change);
exit 1 when plugin content changed without a CHANGELOG.md change.

Config: reads engram.hooks.json key `changelog_check`:
  {
    "content_globs": ["<glob>", ...],   # what counts as shippable content
    "changelog": "CHANGELOG.md",         # basename that satisfies the check
    "ignore_globs": ["<glob>", ...]      # never count these as content
  }
Built-in defaults so it works with no config present.

Pure Python 3 stdlib, cross-platform.
"""
import os
import sys
import json
import fnmatch
import subprocess

DEFAULTS = {
    "changelog": "CHANGELOG.md",
    "content_globs": [
        "plugins/**",
        "skills/**",
        "tools/**",
        "hooks/**",
        "**/*.py",
    ],
    "ignore_globs": [
        "**/CHANGELOG.md",
        "**/__pycache__/**",
        "**/*.pyc",
        "**/*_test.py",
        "**/test_*.py",
        "**/*.md",
    ],
}


def _die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def _find_config(start):
    d = os.path.abspath(start)
    while True:
        for rel in ("engram.hooks.json",
                    os.path.join("hooks", "engram.hooks.json"),
                    os.path.join("plugins", "engram", "hooks", "engram.hooks.json")):
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return (json.load(f).get("changelog_check") or {})
                except Exception:
                    return {}
        parent = os.path.dirname(d)
        if parent == d:
            return {}
        d = parent


def _cfg(start):
    c = dict(DEFAULTS)
    c.update(_find_config(start))
    return c


def _git(repo_root, args):
    return subprocess.run(["git", "-C", repo_root] + args,
                          capture_output=True, text=True, check=False)


def _repo_root(path):
    r = _git(path if os.path.isdir(path) else os.path.dirname(path),
             ["rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def changed_files(repo_root, staged_only):
    out = set()
    r = _git(repo_root, ["diff", "--name-only", "--cached"])
    if r.returncode == 0:
        out.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    if not staged_only:
        r2 = _git(repo_root, ["diff", "--name-only"])
        if r2.returncode == 0:
            out.update(x.strip() for x in r2.stdout.splitlines() if x.strip())
        # untracked files too — new plugin content that isn't staged yet
        r3 = _git(repo_root, ["ls-files", "--others", "--exclude-standard"])
        if r3.returncode == 0:
            out.update(x.strip() for x in r3.stdout.splitlines() if x.strip())
    return {p.replace("\\", "/") for p in out}


def _match_any(path, globs):
    p = path.replace("\\", "/")
    for g in globs:
        g = g.replace("\\", "/")
        if fnmatch.fnmatch(p, g):
            return True
        if g.startswith("**/") and fnmatch.fnmatch(p, g[3:]):
            return True
    return False


def analyze(changed, cfg):
    """Return (content_paths, changelog_present: bool)."""
    changelog = cfg.get("changelog", DEFAULTS["changelog"]).replace("\\", "/")
    content_globs = cfg.get("content_globs", DEFAULTS["content_globs"])
    ignore_globs = cfg.get("ignore_globs", DEFAULTS["ignore_globs"])

    changelog_present = any(
        os.path.basename(p).lower() == os.path.basename(changelog).lower()
        for p in changed)

    content = []
    for p in sorted(changed):
        if os.path.basename(p).lower() == os.path.basename(changelog).lower():
            continue
        if _match_any(p, ignore_globs):
            continue
        if _match_any(p, content_globs):
            content.append(p)
    return content, changelog_present


def run(repo, staged_only):
    root = _repo_root(repo)
    if not root:
        _die("changelog_check: not a git repo: %s" % repo)
    cfg = _cfg(repo)
    changed = changed_files(root, staged_only)
    content, changelog_present = analyze(changed, cfg)

    if not content:
        print("changelog_check: OK — no plugin content changed.")
        return 0
    if changelog_present:
        print("changelog_check: OK — %d content file(s) changed and %s is updated."
              % (len(content), cfg.get("changelog", "CHANGELOG.md")))
        return 0

    sys.stderr.write("CHANGELOG MISSING (advisory): plugin content changed but %s did not\n"
                     % cfg.get("changelog", "CHANGELOG.md"))
    for p in content[:20]:
        sys.stderr.write("  - %s\n" % p)
    if len(content) > 20:
        sys.stderr.write("  ... and %d more\n" % (len(content) - 20))
    sys.stderr.write("  Fix: add an entry to %s describing this change (or add it "
                     "to ignore_globs if it isn't shippable).\n"
                     % cfg.get("changelog", "CHANGELOG.md"))
    return 1


def selftest():
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="changelog_")
    ok = True

    def git(args):
        return subprocess.run(["git", "-C", tmp] + args,
                              capture_output=True, text=True, check=False)

    def write(rel, text):
        p = os.path.join(tmp, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p) or tmp, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    try:
        git(["init", "-q"])
        git(["config", "user.email", "t@example.com"])
        git(["config", "user.name", "t"])
        git(["config", "commit.gpgsign", "false"])

        write("plugins/engram/tools/a.py", "x = 1\n")
        write("CHANGELOG.md", "# Changelog\n")
        write("README.md", "readme\n")
        git(["add", "-A"])
        c = git(["commit", "-q", "-m", "base"])
        assert c.returncode == 0, "base commit failed: %s" % c.stderr

        cfg = dict(DEFAULTS)

        # Case A: content changed, CHANGELOG NOT changed -> warn (exit 1)
        write("plugins/engram/tools/a.py", "x = 2\n")
        git(["add", "-A"])
        changed = changed_files(tmp, staged_only=False)
        content, present = analyze(changed, cfg)
        assert content and not present, \
            "content without changelog must flag; got content=%r present=%r" % (content, present)
        assert run(tmp, staged_only=False) == 1, "missing changelog must exit 1"

        # Case B: content changed AND CHANGELOG changed -> OK (exit 0)
        write("CHANGELOG.md", "# Changelog\n- bump a.py\n")
        git(["add", "-A"])
        changed = changed_files(tmp, staged_only=False)
        content, present = analyze(changed, cfg)
        assert content and present, "changelog present should satisfy"
        assert run(tmp, staged_only=False) == 0, "content + changelog exits 0"

        # Case C: only a non-content file (README/docs) changed -> OK (exit 0)
        git(["commit", "-q", "-m", "sync"])
        write("README.md", "readme v2\n")
        git(["add", "-A"])
        changed = changed_files(tmp, staged_only=False)
        content, present = analyze(changed, cfg)
        assert content == [], "docs-only change is not content; got %r" % content
        assert run(tmp, staged_only=False) == 0, "docs-only exits 0"

        # Case D: ignore_globs excludes pyc / __pycache__ / tests
        git(["commit", "-q", "-m", "readme"])
        write("plugins/engram/tools/__pycache__/a.pyc", "junk\n")
        write("plugins/engram/tools/test_a.py", "def test(): pass\n")
        git(["add", "-A"])
        changed = changed_files(tmp, staged_only=False)
        content, present = analyze(changed, cfg)
        assert content == [], "pycache + tests must be ignored; got %r" % content

        # Case E: untracked new content file is detected (not staged)
        write("plugins/engram/skills/new/SKILL.md", "hi\n")
        # note: SKILL.md is *.md which is ignored, so use a .py to prove content detection
        write("plugins/engram/tools/brand_new.py", "y = 1\n")
        changed = changed_files(tmp, staged_only=False)
        content, present = analyze(changed, cfg)
        assert any(p.endswith("brand_new.py") for p in content), \
            "untracked new .py content must be detected; got %r" % content

        print("SELFTEST changelog_check: PASS")
    except AssertionError as e:
        ok = False
        print("SELFTEST changelog_check: FAIL -", e)
    except Exception as e:
        ok = False
        print("SELFTEST changelog_check: FAIL - unexpected:", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        sys.exit(selftest())
    staged_only = "--staged" in argv
    pos = [a for a in argv if not a.startswith("--")]
    if not pos:
        _die("usage: changelog_check.py <repo> [--staged]")
    sys.exit(run(pos[0], staged_only))


if __name__ == "__main__":
    main(sys.argv[1:])
