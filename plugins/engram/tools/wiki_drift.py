#!/usr/bin/env python3
"""Wiki drift check — did app code change without its Wiki page?

When source changes but the documentation that describes it doesn't, the docs
silently rot. This tool diffs a git ref, maps each changed app-code path to the
Wiki page that documents it, and WARNS (non-zero) for every mapping whose app
code changed but whose Wiki page did NOT change in the same diff.

Advisory only: it flags drift, it does not block. Wire it into pre-commit as a
warning if you want.

Usage:
  python wiki_drift.py <repo> [--since <gitref>]

  <repo>          path inside the git repo to check.
  --since <ref>   compare working tree against this ref (default: HEAD, i.e.
                  staged + unstaged changes). Any git ref works, e.g.
                  origin/main, a tag, or a commit SHA.

Exit 0 when no drift; exit 1 when >= 1 mapped page drifted (advisory warning).

Config: reads engram.hooks.json key `wiki_drift`:
  {
    "map": [ {"code": "<glob>", "wiki": "<Wiki/page.md>"}, ... ],
    "wiki_dir": "Wiki"
  }
Each rule maps a code glob to the Wiki page that documents it. With no config,
a built-in default maps common app-code globs to `Wiki/<name>.md`. A `Raw/
manifest` file (JSON list of {code, wiki}) at the repo root is also honored if
present.

Pure Python 3 stdlib, cross-platform.
"""
import os
import re
import sys
import json
import fnmatch
import subprocess

DEFAULTS = {
    "wiki_dir": "Wiki",
    # code glob -> wiki page. Order matters; first matching rule wins per file.
    "map": [
        {"code": "**/models/**", "wiki": "Wiki/Models.md"},
        {"code": "**/models.py", "wiki": "Wiki/Models.md"},
        {"code": "**/views/**", "wiki": "Wiki/Views.md"},
        {"code": "**/views.py", "wiki": "Wiki/Views.md"},
        {"code": "**/consumers.py", "wiki": "Wiki/Consumers.md"},
        {"code": "**/handlers/**", "wiki": "Wiki/Handlers.md"},
        {"code": "**/settings.py", "wiki": "Wiki/Settings.md"},
        {"code": "**/settings/**", "wiki": "Wiki/Settings.md"},
        {"code": "**/urls.py", "wiki": "Wiki/Routing.md"},
        {"code": "**/api/**", "wiki": "Wiki/API.md"},
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
                return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _load_manifest(repo_root):
    """Honor a Raw/manifest file: a JSON list of {code, wiki} rules."""
    for name in ("manifest", "manifest.json"):
        p = os.path.join(repo_root, "Raw", name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [r for r in data if isinstance(r, dict) and "code" in r and "wiki" in r]
            except Exception:
                return None
    return None


def _cfg(start, repo_root):
    c = dict(DEFAULTS)
    p = _find_config(start)
    if p:
        try:
            with open(p, encoding="utf-8") as f:
                wd = (json.load(f).get("wiki_drift") or {})
            c.update(wd)
        except Exception:
            pass
    manifest = _load_manifest(repo_root)
    if manifest:
        c = dict(c)
        c["map"] = manifest
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


def changed_files(repo_root, since):
    """Return a set of repo-relative changed paths (posix separators).

    Compares the working tree (incl. staged) against `since`. Falls back to
    diffing staged-only if `since` is unresolvable.
    """
    out = set()
    r = _git(repo_root, ["diff", "--name-only", since])
    if r.returncode == 0:
        out.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    # include staged changes not yet reflected against the ref
    r2 = _git(repo_root, ["diff", "--name-only", "--cached", since])
    if r2.returncode == 0:
        out.update(x.strip() for x in r2.stdout.splitlines() if x.strip())
    return {p.replace("\\", "/") for p in out}


def _matches(path, glob):
    g = glob.replace("\\", "/")
    p = path.replace("\\", "/")
    if fnmatch.fnmatch(p, g):
        return True
    # allow '**/x' to also match a top-level 'x'
    if g.startswith("**/") and fnmatch.fnmatch(p, g[3:]):
        return True
    return False


def _is_wiki(path, wiki_dir):
    return path.replace("\\", "/").lower().startswith(wiki_dir.replace("\\", "/").lower().rstrip("/") + "/") \
        or path.replace("\\", "/").lower().startswith(wiki_dir.replace("\\", "/").lower().rstrip("/"))


def analyze(changed, cfg):
    """Return list of drift tuples (code_path, wiki_page) for warnings."""
    rules = cfg.get("map") or []
    wiki_changed = {p.replace("\\", "/") for p in changed}
    drifts = []
    seen = set()
    for path in sorted(changed):
        for rule in rules:
            if _matches(path, rule["code"]):
                wiki = rule["wiki"].replace("\\", "/")
                if wiki not in wiki_changed:
                    key = (path, wiki)
                    if key not in seen:
                        seen.add(key)
                        drifts.append(key)
                break  # first matching rule wins for this file
    return drifts


def run(repo, since):
    root = _repo_root(repo)
    if not root:
        _die("wiki_drift: not a git repo: %s" % repo)
    cfg = _cfg(repo, root)
    changed = changed_files(root, since)
    if not changed:
        print("wiki_drift: no changes vs %s — nothing to check." % since)
        return 0
    drifts = analyze(changed, cfg)
    if not drifts:
        print("wiki_drift: OK — all changed app code has matching Wiki changes "
              "(vs %s)." % since)
        return 0
    sys.stderr.write("WIKI DRIFT (advisory): app code changed but its Wiki page did not\n")
    for code, wiki in drifts:
        sys.stderr.write("  - %s  ->  %s (unchanged)\n" % (code, wiki))
    sys.stderr.write("  Fix: update the mapped Wiki page in the SAME change, "
                     "or adjust the wiki_drift map in engram.hooks.json.\n")
    return 1


def selftest():
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="wikidrift_")
    ok = True

    def git(args):
        return subprocess.run(["git", "-C", tmp] + args,
                              capture_output=True, text=True, check=False)

    def write(rel, text):
        p = os.path.join(tmp, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    try:
        git(["init", "-q"])
        git(["config", "user.email", "t@example.com"])
        git(["config", "user.name", "t"])
        git(["config", "commit.gpgsign", "false"])

        write("app/models.py", "class A: pass\n")
        write("Wiki/Models.md", "# Models\nA\n")
        write("app/views.py", "def v(): pass\n")
        write("Wiki/Views.md", "# Views\n")
        git(["add", "-A"])
        c = git(["commit", "-q", "-m", "base"])
        assert c.returncode == 0, "base commit failed: %s" % c.stderr

        cfg = dict(DEFAULTS)

        # Case A: change models.py but NOT Wiki/Models.md -> drift
        write("app/models.py", "class A:\n    x = 1\n")
        git(["add", "-A"])
        changed = changed_files(tmp, "HEAD")
        drifts = analyze(changed, cfg)
        assert any(w == "Wiki/Models.md" for _, w in drifts), \
            "models.py change without Wiki/Models.md must drift; got %r" % drifts
        assert run(tmp, "HEAD") == 1, "drift case must exit 1"

        # Case B: change models.py AND its wiki -> no drift for that page
        write("Wiki/Models.md", "# Models\nA (updated)\n")
        git(["add", "-A"])
        changed = changed_files(tmp, "HEAD")
        drifts = analyze(changed, cfg)
        assert not any(w == "Wiki/Models.md" for _, w in drifts), \
            "wiki updated alongside code must NOT drift; got %r" % drifts
        assert run(tmp, "HEAD") == 0, "no-drift case must exit 0"

        # Case C: unmapped file changed -> no drift, exit 0
        git(["commit", "-q", "-m", "sync models"])
        write("README.md", "hello\n")
        git(["add", "-A"])
        changed = changed_files(tmp, "HEAD")
        assert analyze(changed, cfg) == [], "unmapped file must not drift"
        assert run(tmp, "HEAD") == 0, "unmapped-only change exits 0"

        # Case D: Raw/manifest overrides the default map
        write("Raw/manifest", json.dumps(
            [{"code": "**/service.py", "wiki": "Wiki/Service.md"}]))
        write("app/service.py", "def s(): pass\n")
        git(["add", "-A"])
        c2 = _cfg(tmp, tmp)
        assert c2["map"] == [{"code": "**/service.py", "wiki": "Wiki/Service.md"}], \
            "Raw/manifest must override map; got %r" % c2["map"]
        changed = changed_files(tmp, "HEAD")
        drifts = analyze(changed, c2)
        assert any(w == "Wiki/Service.md" for _, w in drifts), \
            "manifest-mapped drift must fire; got %r" % drifts

        print("SELFTEST wiki_drift: PASS")
    except AssertionError as e:
        ok = False
        print("SELFTEST wiki_drift: FAIL -", e)
    except Exception as e:  # e.g. git not installed
        ok = False
        print("SELFTEST wiki_drift: FAIL - unexpected:", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def _opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        _die("%s needs a value." % name)
    return default


def main(argv):
    if "--selftest" in argv:
        sys.exit(selftest())
    since = _opt(argv, "--since", "HEAD")
    flags = {"--since"}
    pos = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in flags:
            skip = True
            continue
        if a.startswith("--"):
            continue
        pos.append(a)
    if not pos:
        _die("usage: wiki_drift.py <repo> [--since <gitref>]")
    sys.exit(run(pos[0], since))


if __name__ == "__main__":
    main(sys.argv[1:])
