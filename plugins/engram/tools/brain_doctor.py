#!/usr/bin/env python3
"""Brain doctor — one aggregate health check for an Engram-wired repo.

Runs a battery of independent checks and prints a single PASS/WARN/FAIL table.

  python brain_doctor.py [REPO_DIR]     health-check REPO_DIR (default: cwd's repo)
  python brain_doctor.py --json [REPO]  machine-readable result
  python brain_doctor.py --selftest     build temp fixtures, assert behaviour

Checks (each degrades gracefully if its inputs are absent):
  git-hooks       core.hooksPath points at the shipped hooks/git dir, OR the
                  three hook entrypoints are copied into the repo's hooks dir.
  cc-hooks        Claude Code hooks config (hooks.json) is present + parseable.
  parity          capabilities.md Layer-A ids  <->  skills/<id>/ dirs match.
                  Delegates to a sibling parity_check.py if one ships; else
                  compares the sets inline.
  version-canon   plugin manifest version == newest CHANGELOG version (and any
                  sibling version_canon.py agrees). Delegates if present.
  locks           tamper snapshots / *.lock / *.locked present and fresh, IF the
                  repo opts into them (seal/tamper config). N/A otherwise.
  gitignore       .gitignore covers env/secret files.

Exit 0 if no FAIL; exit 1 if any check FAILs. WARN never fails the run.
Pure Python 3 stdlib. Cross-platform (Windows / macOS / Linux).
"""
import os
import sys
import re
import json
import time
import subprocess

# ---- result vocabulary ------------------------------------------------------
PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"


class Result:
    __slots__ = ("name", "status", "detail")

    def __init__(self, name, status, detail=""):
        self.name = name
        self.status = status
        self.detail = detail


# ---- generic helpers --------------------------------------------------------
def _git(root, *a, check=False):
    try:
        r = subprocess.run(["git", "-C", root, *a],
                           capture_output=True, text=True)
    except (OSError, FileNotFoundError):
        return "", 127
    if check and r.returncode != 0:
        return (r.stderr or r.stdout).strip(), r.returncode
    return r.stdout.strip(), r.returncode


def _repo_root(start):
    out, rc = _git(start, "rev-parse", "--show-toplevel")
    if rc == 0 and out:
        return out
    # not a git repo (or no git): fall back to the dir itself so the other
    # checks can still run.
    return os.path.abspath(start)


def _plugin_root(here):
    """Locate the plugin root (dir holding capabilities.md / skills/ / hooks/)
    by walking up from this file. Returns None if not found."""
    d = os.path.dirname(os.path.abspath(here))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "skills")) and \
           os.path.isfile(os.path.join(d, "capabilities.md")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def _load_config(plugin_root):
    """Best-effort read of hooks/engram.hooks.json (for gitignore/secret hints)."""
    cfg = {}
    if not plugin_root:
        return cfg
    p = os.path.join(plugin_root, "hooks", "engram.hooks.json")
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    return cfg


def _first_line(text, limit=88):
    """First non-empty line of a tool's output, ASCII-clamped for console
    safety on legacy codepages, truncated."""
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if ln:
            ln = ln.encode("ascii", "replace").decode("ascii")
            return ln[:limit]
    return ""


def _run_sibling(path, *args):
    """Run a sibling tool; return (returncode, combined_output) or None if
    it doesn't exist / can't run."""
    if not path or not os.path.isfile(path):
        return None
    try:
        r = subprocess.run([sys.executable, path, *args],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode, (r.stdout + r.stderr).strip()


# ---- individual checks ------------------------------------------------------
def check_git_hooks(root, plugin_root):
    """core.hooksPath -> shipped git dir, OR entrypoints copied into repo."""
    git_src = os.path.join(plugin_root, "hooks", "git") if plugin_root else None
    entrypoints = ("pre-commit", "commit-msg", "pre-push")

    hp, rc = _git(root, "config", "--local", "--get", "core.hooksPath")
    if rc == 0 and hp:
        abs_hp = hp if os.path.isabs(hp) else os.path.join(root, hp)
        if git_src and os.path.abspath(abs_hp) == os.path.abspath(git_src):
            return Result("git-hooks", PASS,
                          "core.hooksPath -> shipped hooks/git")
        # points somewhere; check the entrypoints live there
        if all(os.path.isfile(os.path.join(abs_hp, e)) for e in entrypoints):
            return Result("git-hooks", PASS,
                          "core.hooksPath -> %s (entrypoints present)" % hp)
        return Result("git-hooks", WARN,
                      "core.hooksPath=%s but Engram entrypoints not all found" % hp)

    # no hooksPath: are the hooks copied into the repo's real hooks dir?
    hooks_dir, hrc = _git(root, "rev-parse", "--git-path", "hooks")
    if hrc == 0 and hooks_dir:
        hooks_dir = hooks_dir if os.path.isabs(hooks_dir) \
            else os.path.join(root, hooks_dir)
        present = [e for e in entrypoints
                   if os.path.isfile(os.path.join(hooks_dir, e))]
        if len(present) == len(entrypoints):
            return Result("git-hooks", PASS, "hooks copied into %s" % hooks_dir)
        if present:
            return Result("git-hooks", WARN,
                          "only %d/3 hook entrypoints copied" % len(present))
    return Result("git-hooks", FAIL,
                  "no core.hooksPath and no copied hooks - run hooks/install.py")


def check_cc_hooks(root, plugin_root):
    """Claude Code hooks.json present + parseable. Look in the plugin (shipped
    definition) and in the repo's .claude/ (project-level wiring)."""
    candidates = []
    if plugin_root:
        candidates.append(os.path.join(plugin_root, "hooks", "hooks.json"))
        candidates.append(os.path.join(plugin_root, "hooks", "engram.hooks.json"))
    candidates.append(os.path.join(root, ".claude", "settings.json"))
    candidates.append(os.path.join(root, ".claude", "settings.local.json"))

    found_valid = []
    found_bad = []
    for c in candidates:
        if not os.path.isfile(c):
            continue
        try:
            with open(c, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            found_bad.append((c, str(e)))
            continue
        if isinstance(data, dict) and "hooks" in data:
            found_valid.append(c)
        elif c.endswith((".claude/settings.json", ".claude/settings.local.json")):
            # present but no hooks block yet — note it but don't count as valid
            pass
    if found_bad:
        c, e = found_bad[0]
        return Result("cc-hooks", FAIL,
                      "unparseable %s (%s)" % (os.path.basename(c), e.split(':')[0]))
    if found_valid:
        return Result("cc-hooks", PASS,
                      "hooks config: %s" % os.path.basename(found_valid[0]))
    return Result("cc-hooks", WARN,
                  "no Claude Code hooks block found - paste the install snippet")


def _parse_capabilities(plugin_root):
    """Extract Layer-A capability ids from capabilities.md (backtick-quoted ids
    in table rows). Returns a set (empty if file missing)."""
    ids = set()
    if not plugin_root:
        return ids
    p = os.path.join(plugin_root, "capabilities.md")
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        return ids
    # only scan the Layer A section if it's delimited; else whole file
    m = re.search(r"##\s*Layer A.*?(?=\n##\s|\Z)", text, re.S | re.I)
    scope = m.group(0) if m else text
    for row in scope.splitlines():
        row = row.strip()
        if not row.startswith("|"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not cells:
            continue
        cm = re.match(r"`([a-z0-9][a-z0-9-]*)`", cells[0])
        if cm:
            ids.add(cm.group(1))
    return ids


def _skill_dirs(plugin_root):
    if not plugin_root:
        return set()
    sk = os.path.join(plugin_root, "skills")
    if not os.path.isdir(sk):
        return set()
    return {d for d in os.listdir(sk)
            if os.path.isdir(os.path.join(sk, d)) and not d.startswith(".")}


def check_parity(root, plugin_root):
    """capabilities <-> skills. Delegate to parity_check.py if it ships."""
    sib = os.path.join(plugin_root, "tools", "parity_check.py") \
        if plugin_root else None
    delegated = _run_sibling(sib, plugin_root or ".")
    if delegated is not None:
        rc, out = delegated
        return Result("parity", PASS if rc == 0 else FAIL,
                      "parity_check.py -> " + (_first_line(out) or "rc=%d" % rc))

    caps = _parse_capabilities(plugin_root)
    skills = _skill_dirs(plugin_root)
    if not caps and not skills:
        return Result("parity", NA, "no capabilities.md / skills to compare")
    missing_skill = sorted(caps - skills)      # declared but no dir
    undeclared = sorted(skills - caps)         # dir but not declared
    if not missing_skill and not undeclared:
        return Result("parity", PASS, "%d capabilities all have skills" % len(caps))
    bits = []
    if missing_skill:
        bits.append("declared w/o skill: " + ", ".join(missing_skill))
    if undeclared:
        bits.append("skill w/o capability row: " + ", ".join(undeclared))
    # declared-without-skill is a hard break; extra skills are a WARN
    status = FAIL if missing_skill else WARN
    return Result("parity", status, "; ".join(bits))


def _manifest_version(plugin_root):
    if not plugin_root:
        return None
    for rel in (os.path.join(".claude-plugin", "plugin.json"),
                "plugin.json"):
        p = os.path.join(plugin_root, rel)
        if os.path.isfile(p):
            try:
                v = json.load(open(p, encoding="utf-8")).get("version")
                if v:
                    return str(v).strip()
            except (OSError, ValueError):
                pass
    return None


def _changelog_version(plugin_root):
    if not plugin_root:
        return None
    p = os.path.join(plugin_root, "CHANGELOG.md")
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"^\s*##\s*\[?v?(\d+\.\d+\.\d+[^\]\s]*)\]?", text, re.M)
    return m.group(1) if m else None


def check_version_canon(root, plugin_root):
    """Delegate to version_canon.py if present; else compare manifest vs
    CHANGELOG top version."""
    sib = os.path.join(plugin_root, "tools", "version_canon.py") \
        if plugin_root else None
    delegated = _run_sibling(sib, plugin_root or ".")
    if delegated is not None:
        rc, out = delegated
        return Result("version-canon", PASS if rc == 0 else FAIL,
                      "version_canon.py -> " + (_first_line(out) or "rc=%d" % rc))

    mv = _manifest_version(plugin_root)
    cv = _changelog_version(plugin_root)
    if mv is None and cv is None:
        return Result("version-canon", NA, "no manifest / CHANGELOG version")
    if mv is None or cv is None:
        return Result("version-canon", WARN,
                      "manifest=%s changelog=%s (one missing)" % (mv, cv))
    if mv == cv:
        return Result("version-canon", PASS, "v%s (manifest == changelog)" % mv)
    return Result("version-canon", FAIL,
                  "manifest v%s != changelog v%s" % (mv, cv))


def _collect_lock_specs(root, plugin_root):
    """Return list of (label, path) lock/snapshot files the repo opts into,
    from an engram.config.json if present. Empty => feature not in use."""
    specs = []
    # look for a repo-level seal/tamper config (opt-in)
    for name in ("engram.config.json",):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                cfg = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            base = os.path.join(root, cfg.get("root", "."))
            seal = cfg.get("seal", {})
            if seal.get("locked_file"):
                specs.append(("seal.locked", os.path.join(base, seal["locked_file"])))
            tamper = cfg.get("tamper", {})
            if tamper.get("structure_lock"):
                specs.append(("structure.lock",
                              os.path.join(base, tamper["structure_lock"])))
            ao = cfg.get("append_only", {})
            if ao.get("lock"):
                specs.append(("append-only.lock", os.path.join(base, ao["lock"])))
    return specs


def check_locks(root, plugin_root, fresh_days=90):
    """If the repo opts into tamper snapshots (*.lock/*.locked), each must
    exist and be reasonably fresh. If not opted in, N/A."""
    specs = _collect_lock_specs(root, plugin_root)
    if not specs:
        return Result("locks", NA, "no tamper/lock config - feature not in use")
    missing, stale, ok = [], [], []
    now = time.time()
    for label, path in specs:
        if not os.path.isfile(path):
            missing.append(label)
            continue
        age_days = (now - os.path.getmtime(path)) / 86400.0
        if age_days > fresh_days:
            stale.append("%s (%dd old)" % (label, int(age_days)))
        else:
            ok.append(label)
    if missing:
        return Result("locks", FAIL, "missing snapshot(s): " + ", ".join(missing))
    if stale:
        return Result("locks", WARN, "stale: " + ", ".join(stale))
    return Result("locks", PASS, "%d snapshot(s) fresh" % len(ok))


def check_gitignore(root, plugin_root, cfg):
    """.gitignore covers env/secret files."""
    p = os.path.join(root, ".gitignore")
    if not os.path.isfile(p):
        return Result("gitignore", FAIL, "no .gitignore - env/secrets unguarded")
    try:
        lines = [ln.strip() for ln in open(p, encoding="utf-8")
                 if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return Result("gitignore", WARN, ".gitignore unreadable")
    joined = "\n".join(lines).lower()
    # what we want covered: .env family + generic secrets
    wants = {
        "env": bool(re.search(r"(^|/|\*)\.env\b|\.env($|\*|\.)", joined)
                    or ".env" in lines),
        "secrets": ("secret" in joined or "*.key" in joined
                    or "*.pem" in joined or "credentials" in joined),
    }
    missing = [k for k, v in wants.items() if not v]
    if not missing:
        return Result("gitignore", PASS, "covers env + secrets")
    if "env" in missing:
        return Result("gitignore", FAIL,
                      "does NOT ignore .env (dotenv secrets can be committed)")
    return Result("gitignore", WARN, "no explicit secret/*.key/*.pem/creds rule")


# ---- orchestration ----------------------------------------------------------
def run_all(root, plugin_root):
    cfg = _load_config(plugin_root)
    checks = [
        check_git_hooks(root, plugin_root),
        check_cc_hooks(root, plugin_root),
        check_parity(root, plugin_root),
        check_version_canon(root, plugin_root),
        check_locks(root, plugin_root),
        check_gitignore(root, plugin_root, cfg),
    ]
    return checks


_GLYPH = {PASS: "[PASS]", WARN: "[WARN]", FAIL: "[FAIL]", NA: "[ N/A]"}


def print_table(root, plugin_root, checks):
    print("=" * 66)
    print("  Engram brain doctor")
    print("  repo:   %s" % root)
    print("  plugin: %s" % (plugin_root or "(not found)"))
    print("=" * 66)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print("  %s  %-*s  %s" % (_GLYPH[c.status], width, c.name, c.detail))
    print("-" * 66)
    n_fail = sum(1 for c in checks if c.status == FAIL)
    n_warn = sum(1 for c in checks if c.status == WARN)
    n_pass = sum(1 for c in checks if c.status == PASS)
    n_na = sum(1 for c in checks if c.status == NA)
    print("  %d PASS | %d WARN | %d FAIL | %d N/A" %
          (n_pass, n_warn, n_fail, n_na))
    if n_fail:
        print("  RESULT: FAIL - fix the [FAIL] rows above.")
    elif n_warn:
        print("  RESULT: OK with warnings.")
    else:
        print("  RESULT: healthy.")
    print("=" * 66)
    return n_fail


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    as_json = "--json" in argv
    positional = [a for a in argv if not a.startswith("-")]
    start = positional[0] if positional else os.getcwd()
    root = _repo_root(start)
    plugin_root = _plugin_root(__file__)
    checks = run_all(root, plugin_root)
    n_fail = sum(1 for c in checks if c.status == FAIL)
    if as_json:
        print(json.dumps({
            "repo": root,
            "plugin_root": plugin_root,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                       for c in checks],
            "result": "FAIL" if n_fail else "OK",
        }, indent=2))
    else:
        print_table(root, plugin_root, checks)
    return 1 if n_fail else 0


# ---- self-test --------------------------------------------------------------
def _selftest():
    import tempfile
    import shutil
    failures = []

    def expect(cond, msg):
        if not cond:
            failures.append(msg)
            print("  FAIL:", msg)
        else:
            print("  ok  :", msg)

    tmp = tempfile.mkdtemp(prefix="brain_doctor_selftest_")
    try:
        # --- fixture A: a repo with NOTHING wired -------------------------
        repo = os.path.join(tmp, "bare")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo],
                       capture_output=True, text=True)
        # fake plugin root so parity/version checks have inputs
        plug = os.path.join(tmp, "plugin")
        os.makedirs(os.path.join(plug, "skills", "alpha"))
        os.makedirs(os.path.join(plug, "skills", "beta"))
        os.makedirs(os.path.join(plug, "hooks", "git"))
        os.makedirs(os.path.join(plug, ".claude-plugin"))
        with open(os.path.join(plug, "capabilities.md"), "w", encoding="utf-8") as f:
            f.write("# caps\n\n## Layer A\n\n| id | x |\n|---|---|\n"
                    "| `alpha` | a |\n| `beta` | b |\n\n## Layer B\n")
        with open(os.path.join(plug, ".claude-plugin", "plugin.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"version": "2.0.0"}, f)
        with open(os.path.join(plug, "CHANGELOG.md"), "w", encoding="utf-8") as f:
            f.write("# cl\n\n## [2.0.0] — 2026-01-01\n- x\n")
        with open(os.path.join(plug, "hooks", "hooks.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"hooks": {"SessionStart": []}}, f)
        for e in ("pre-commit", "commit-msg", "pre-push"):
            with open(os.path.join(plug, "hooks", "git", e),
                      "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")

        r = _repo_root(repo)
        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["git-hooks"].status == FAIL,
               "bare repo -> git-hooks FAIL (no hooksPath, none copied)")
        expect(checks["parity"].status == PASS,
               "matching caps/skills -> parity PASS")
        expect(checks["version-canon"].status == PASS,
               "manifest==changelog -> version-canon PASS")
        expect(checks["gitignore"].status == FAIL,
               "no .gitignore -> gitignore FAIL")
        expect(checks["locks"].status == NA,
               "no lock config -> locks N/A")
        n_fail = sum(1 for c in checks.values() if c.status == FAIL)
        expect(n_fail > 0, "aggregate has FAILs -> nonzero exit")

        # --- fixture B: a fully-wired repo --------------------------------
        subprocess.run(["git", "-C", repo, "config", "--local",
                        "core.hooksPath", os.path.join(plug, "hooks", "git")],
                       capture_output=True, text=True)
        with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("# secrets\n.env\n*.pem\nsecrets.*\n")
        # opt into a lock + create a fresh snapshot
        with open(os.path.join(repo, "engram.config.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"root": ".", "tamper": {"structure_lock": "structure.lock"}}, f)
        with open(os.path.join(repo, "structure.lock"), "w", encoding="utf-8") as f:
            f.write("{}\n")

        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["git-hooks"].status == PASS,
               "hooksPath set -> git-hooks PASS")
        expect(checks["gitignore"].status == PASS,
               ".env+*.pem+secrets.* -> gitignore PASS")
        expect(checks["locks"].status == PASS,
               "fresh structure.lock -> locks PASS")
        n_fail = sum(1 for c in checks.values() if c.status == FAIL)
        expect(n_fail == 0, "wired repo -> zero FAILs -> exit 0")

        # --- fixture C: parity + version drift ----------------------------
        os.makedirs(os.path.join(plug, "skills", "gamma"))  # undeclared skill
        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["parity"].status == WARN,
               "extra skill dir -> parity WARN (not a hard fail)")
        # declared-without-skill should be FAIL
        shutil.rmtree(os.path.join(plug, "skills", "beta"))
        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["parity"].status == FAIL,
               "capability with no skill dir -> parity FAIL")
        # break version canon
        with open(os.path.join(plug, ".claude-plugin", "plugin.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"version": "9.9.9"}, f)
        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["version-canon"].status == FAIL,
               "manifest!=changelog -> version-canon FAIL")

        # --- fixture D: stale lock ----------------------------------------
        old = time.time() - 200 * 86400
        os.utime(os.path.join(repo, "structure.lock"), (old, old))
        checks = {c.name: c for c in run_all(r, plug)}
        expect(checks["locks"].status == WARN,
               "old snapshot -> locks WARN (stale, not missing)")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 50)
    if failures:
        print("SELFTEST FAILED: %d assertion(s)" % len(failures))
        return 1
    print("SELFTEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
