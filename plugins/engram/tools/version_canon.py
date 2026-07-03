#!/usr/bin/env python3
"""Version canon — one version, everywhere it's declared.

Asserts a single version string is consistent across the files that declare it:
  * plugin.json                      -> "version"
  * marketplace.json                 -> "metadata.version"  (falls back to "version")
  * CHANGELOG.md                     -> top `## [x.y.z]` entry
  * any extra files declared in config (see below)

  python version_canon.py <plugin_dir>
  python version_canon.py --selftest

<plugin_dir> is searched for the standard files; the marketplace.json is looked
up at <plugin_dir>/.claude-plugin/marketplace.json, <plugin_dir>/marketplace.json,
and one/two levels up (repo-root layout: repo/.claude-plugin/marketplace.json).

Prints every source + its version; if they disagree, prints the mismatch and
exits non-zero. If a source is missing it is skipped (not a mismatch) unless it
is the ONLY source — then there is nothing to check and it passes with a note.

Config (optional) under "version_canon" in engram.hooks.json
(<plugin_dir>/hooks/engram.hooks.json or <plugin_dir>/engram.hooks.json):
  version_canon.extra
    [ { "file": "docs/x.md", "type": "json|changelog|regex",
        "key": "a.b.c" (json), "pattern": "v(\\d+\\.\\d+\\.\\d+)" (regex) } ]
"""
import os
import sys
import re
import json

# `## [1.2.3] — 2026-07-03`  (dash/em-dash/whatever after the bracket)
CHANGELOG_RE = re.compile(r"^\s*##\s*\[([0-9][0-9A-Za-z.\-+]*)\]")
SEMVER_TOKEN = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.\-+]*)")


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def _json_get(data, dotted):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur if isinstance(cur, str) else None


def _changelog_top(path):
    for line in _read(path).splitlines():
        m = CHANGELOG_RE.match(line)
        if m:
            return m.group(1)
    return None


def _load_config(plugin_dir):
    for c in (os.path.join(plugin_dir, "hooks", "engram.hooks.json"),
              os.path.join(plugin_dir, "engram.hooks.json")):
        if os.path.isfile(c):
            try:
                data = json.loads(_read(c))
            except Exception:
                return {}
            sub = data.get("version_canon", {})
            return sub if isinstance(sub, dict) else {}
    return {}


def collect(plugin_dir, cfg):
    """Return list of (label, version_or_None, path_or_reason)."""
    sources = []
    pd = os.path.abspath(plugin_dir)
    parent = os.path.dirname(pd)
    gparent = os.path.dirname(parent)

    # plugin.json
    pj = _first_existing([
        os.path.join(pd, ".claude-plugin", "plugin.json"),
        os.path.join(pd, "plugin.json"),
    ])
    if pj:
        try:
            sources.append(("plugin.json", _json_get(json.loads(_read(pj)),
                                                      "version"), pj))
        except Exception as e:
            sources.append(("plugin.json", None, "parse error: %s" % e))

    # marketplace.json
    mj = _first_existing([
        os.path.join(pd, ".claude-plugin", "marketplace.json"),
        os.path.join(pd, "marketplace.json"),
        os.path.join(parent, ".claude-plugin", "marketplace.json"),
        os.path.join(parent, "marketplace.json"),
        os.path.join(gparent, ".claude-plugin", "marketplace.json"),
    ])
    if mj:
        try:
            data = json.loads(_read(mj))
            v = _json_get(data, "metadata.version") or _json_get(data, "version")
            sources.append(("marketplace.json", v, mj))
        except Exception as e:
            sources.append(("marketplace.json", None, "parse error: %s" % e))

    # CHANGELOG.md
    cl = _first_existing([
        os.path.join(pd, "CHANGELOG.md"),
        os.path.join(parent, "CHANGELOG.md"),
    ])
    if cl:
        sources.append(("CHANGELOG.md(top)", _changelog_top(cl), cl))

    # extra configured sources
    for entry in cfg.get("extra", []) or []:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("file")
        if not rel:
            continue
        fp = rel if os.path.isabs(rel) else os.path.join(pd, rel)
        label = "extra:%s" % rel
        if not os.path.isfile(fp):
            sources.append((label, None, "missing: %s" % fp))
            continue
        typ = entry.get("type", "regex")
        try:
            if typ == "json":
                v = _json_get(json.loads(_read(fp)), entry.get("key", "version"))
            elif typ == "changelog":
                v = _changelog_top(fp)
            else:  # regex
                pat = entry.get("pattern") or SEMVER_TOKEN.pattern
                m = re.search(pat, _read(fp))
                v = m.group(1) if m else None
            sources.append((label, v, fp))
        except Exception as e:
            sources.append((label, None, "error: %s" % e))
    return sources


def run(plugin_dir):
    if not os.path.isdir(plugin_dir):
        sys.stderr.write("version_canon: not a directory: %s\n" % plugin_dir)
        return 2
    cfg = _load_config(plugin_dir)
    sources = collect(plugin_dir, cfg)

    print("version_canon: %s" % plugin_dir)
    found = []
    for label, ver, where in sources:
        if ver:
            print("  %-22s %s" % (label, ver))
            found.append((label, ver))
        else:
            print("  %-22s (none) %s" % (label, where))

    if not found:
        print("version_canon: no version sources found — nothing to check.")
        return 0

    versions = set(v for _, v in found)
    if len(versions) == 1:
        print("version_canon: OK — all agree on %s" % next(iter(versions)))
        return 0

    sys.stderr.write("\nversion_canon FAILED: sources disagree:\n")
    for label, ver in found:
        sys.stderr.write("  %-22s %s\n" % (label, ver))
    sys.stderr.write("Bump every source to the same version before releasing.\n")
    return 1


# --------------------------------------------------------------------------
def _selftest():
    import tempfile
    import shutil

    def build(pv, mv, cv):
        d = tempfile.mkdtemp(prefix="vcanon_")
        os.makedirs(os.path.join(d, ".claude-plugin"), exist_ok=True)
        if pv is not None:
            with open(os.path.join(d, ".claude-plugin", "plugin.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"name": "x", "version": pv}, f)
        if mv is not None:
            with open(os.path.join(d, ".claude-plugin", "marketplace.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"name": "x", "metadata": {"version": mv}}, f)
        if cv is not None:
            with open(os.path.join(d, "CHANGELOG.md"), "w",
                      encoding="utf-8") as f:
                f.write("# Changelog\n\n## [%s] — 2026-07-03\n- stuff\n\n"
                        "## [0.9.0] — 2026-01-01\n- old\n" % cv)
        return d

    fails = []

    # PASS — all three match
    p = build("1.1.0", "1.1.0", "1.1.0")
    if run(p) != 0:
        fails.append("PASS fixture returned nonzero")
    shutil.rmtree(p, ignore_errors=True)

    # FAIL — plugin.json disagrees
    p = build("1.2.0", "1.1.0", "1.1.0")
    if run(p) == 0:
        fails.append("plugin-mismatch returned 0")
    shutil.rmtree(p, ignore_errors=True)

    # FAIL — changelog top disagrees
    p = build("1.1.0", "1.1.0", "1.0.0")
    if run(p) == 0:
        fails.append("changelog-mismatch returned 0")
    srcs = dict((l, v) for l, v, w in collect(p, {}))
    if srcs.get("CHANGELOG.md(top)") != "1.0.0":
        fails.append("changelog top parse wrong: %r" % srcs)
    shutil.rmtree(p, ignore_errors=True)

    # FAIL — marketplace disagrees
    p = build("1.1.0", "2.0.0", "1.1.0")
    if run(p) == 0:
        fails.append("marketplace-mismatch returned 0")
    shutil.rmtree(p, ignore_errors=True)

    # PASS — a source missing is skipped, not a mismatch
    p = build("1.1.0", None, "1.1.0")
    if run(p) != 0:
        fails.append("missing-source (2 agree) returned nonzero")
    shutil.rmtree(p, ignore_errors=True)

    # extra source via config (regex)
    p = build("1.1.0", "1.1.0", "1.1.0")
    with open(os.path.join(p, "README.md"), "w", encoding="utf-8") as f:
        f.write("Engram v1.0.0 rocks\n")  # deliberately stale
    os.makedirs(os.path.join(p, "hooks"), exist_ok=True)
    with open(os.path.join(p, "hooks", "engram.hooks.json"),
              "w", encoding="utf-8") as f:
        json.dump({"version_canon": {"extra": [
            {"file": "README.md", "type": "regex",
             "pattern": "v(\\d+\\.\\d+\\.\\d+)"}]}}, f)
    if run(p) == 0:
        fails.append("extra-regex stale README not caught")
    shutil.rmtree(p, ignore_errors=True)

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("version_canon --selftest: PASS "
          "(pass + plugin/changelog/marketplace mismatch + missing-source "
          "skip + extra-regex)")
    return 0


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.stderr.write("usage: python version_canon.py <plugin_dir> | "
                         "--selftest\n")
        return 2
    return run(args[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
