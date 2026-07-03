#!/usr/bin/env python3
"""Vault lint — health-check an OBrain/Obsidian markdown vault.

Runs three mechanical checks over a vault directory:
  (1) broken [[wikilinks]]  — a link target with no matching note on disk
  (2) orphan notes          — notes with zero inbound wikilinks
  (3) stale backticked paths — a `path/like/this.py` in backticks (in any *.md)
                               that does not exist on disk

Read-only. Prints every issue found to stdout; exits non-zero if any issue exists.

  python vault_lint.py <vault_dir>
  python vault_lint.py <vault_dir> --config path/to/engram.hooks.json
  python vault_lint.py --selftest

Exclusions are configurable via engram.hooks.json under the "vault_lint" key
(auto-discovered at <vault_dir>/../hooks/engram.hooks.json,
<vault_dir>/engram.hooks.json, or passed with --config). Built-in defaults apply
when no config is present. Config keys (all optional):

  vault_lint.exclude_globs   [str]  note stems/paths skipped for ALL checks
                                     (default: ["0000*", "*.template.md"])
  vault_lint.orphan_exempt   [str]  globs whose notes may be orphans w/o flagging
                                     (default: index/MOC-style: ["index*","*INDEX*","README*","MEMORY*","*MOC*"])
  vault_lint.ignore_link_prefixes [str]  wikilink target prefixes to skip as
                                     non-file links (default: ["memory:","http:","https:"])
  vault_lint.path_check_exts [str]  extensions a backticked token must end in to
                                     be treated as a file-path claim
                                     (default: [".py",".js",".ts",".md",".json",".sh",".ps1",".txt",".yaml",".yml",".toml"])

UTF-8 safe: every file is read with encoding='utf-8', errors='replace' so a stray
CP1252 byte never crashes the lint.
"""
import os
import sys
import re
import json
import fnmatch

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
# backticked token that looks like a relative file path: has a / or ends in a known ext
BACKTICK_RE = re.compile(r"`([^`\n]+?)`")

DEFAULTS = {
    "exclude_globs": ["0000*", "*.template.md"],
    "orphan_exempt": ["index*", "*INDEX*", "README*", "MEMORY*", "*MOC*"],
    "ignore_link_prefixes": ["memory:", "http:", "https:", "mailto:"],
    "path_check_exts": [".py", ".js", ".ts", ".md", ".json", ".sh",
                        ".ps1", ".txt", ".yaml", ".yml", ".toml"],
}


def _read(path):
    """UTF-8 read that never raises on a bad byte."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _load_config(vault_dir, explicit):
    cfg = dict(DEFAULTS)
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(os.path.join(vault_dir, "engram.hooks.json"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(vault_dir)),
                                   "hooks", "engram.hooks.json"))
    for c in candidates:
        if c and os.path.isfile(c):
            try:
                data = json.loads(_read(c))
            except Exception:
                continue
            sub = data.get("vault_lint", {})
            if isinstance(sub, dict):
                cfg.update({k: v for k, v in sub.items() if k in DEFAULTS})
            break
    return cfg


def _matches_any(name, globs):
    return any(fnmatch.fnmatch(name, g) for g in globs)


def _collect_notes(vault_dir):
    """Return {stem_lower: relpath} for every *.md, and full list of md relpaths."""
    notes = {}
    md_files = []
    for root, dirs, files in os.walk(vault_dir):
        # skip hidden/system dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if fn.lower().endswith(".md"):
                rel = os.path.relpath(os.path.join(root, fn), vault_dir)
                md_files.append(rel)
                stem = os.path.splitext(fn)[0]
                notes.setdefault(stem.lower(), rel)
    return notes, md_files


def lint(vault_dir, cfg):
    """Return list of (kind, note, detail) issue tuples."""
    notes, md_files = _collect_notes(vault_dir)
    excluded = set(m for m in md_files
                   if _matches_any(os.path.basename(m), cfg["exclude_globs"]))

    issues = []
    inbound = {m: 0 for m in md_files}

    ext_tuple = tuple(cfg["path_check_exts"])

    for rel in md_files:
        if rel in excluded:
            continue
        text = _read(os.path.join(vault_dir, rel))

        # (1) broken wikilinks + tally inbound for (2)
        for m in WIKILINK_RE.finditer(text):
            target = m.group(1).strip()
            if not target:
                continue
            low = target.lower()
            if any(low.startswith(p) for p in cfg["ignore_link_prefixes"]):
                continue
            # resolve by stem (Obsidian short-link) or by relpath
            key = os.path.splitext(os.path.basename(target))[0].lower()
            hit = notes.get(key)
            if hit is None:
                # try full relpath match (with or without .md)
                cand = target if target.lower().endswith(".md") else target + ".md"
                cand_norm = cand.replace("\\", "/").lstrip("./")
                full = None
                for m2 in md_files:
                    if m2.replace("\\", "/").lower() == cand_norm.lower():
                        full = m2
                        break
                if full is None:
                    issues.append(("broken-link", rel, target))
                else:
                    inbound[full] = inbound.get(full, 0) + 1
            else:
                inbound[hit] = inbound.get(hit, 0) + 1

        # (3) stale backticked paths
        for m in BACKTICK_RE.finditer(text):
            tok = m.group(1).strip()
            if not tok or " " in tok:
                continue
            looks_like_path = ("/" in tok or "\\" in tok) and tok.lower().endswith(ext_tuple)
            if not looks_like_path:
                # also flag bare filenames like `foo.py`? no — too noisy; require a separator
                continue
            # strip a trailing :line or #anchor
            clean = re.split(r"[:#]", tok)[0]
            clean = clean.replace("\\", os.sep).replace("/", os.sep)
            # resolve relative to vault_dir AND to the note's own dir
            note_dir = os.path.dirname(os.path.join(vault_dir, rel))
            found = (os.path.exists(os.path.join(vault_dir, clean))
                     or os.path.exists(os.path.join(note_dir, clean)))
            if not found:
                issues.append(("stale-path", rel, tok))

    # (2) orphans — no inbound links, not exempt, not excluded
    for rel in md_files:
        if rel in excluded:
            continue
        base = os.path.basename(rel)
        if _matches_any(base, cfg["orphan_exempt"]):
            continue
        if inbound.get(rel, 0) == 0:
            issues.append(("orphan", rel, "no inbound wikilinks"))

    return issues


def run(vault_dir, config=None):
    if not os.path.isdir(vault_dir):
        sys.stderr.write("vault_lint: not a directory: %s\n" % vault_dir)
        return 2
    cfg = _load_config(vault_dir, config)
    issues = lint(vault_dir, cfg)
    if not issues:
        print("vault_lint: OK — no issues in %s" % vault_dir)
        return 0
    order = {"broken-link": 0, "stale-path": 1, "orphan": 2}
    issues.sort(key=lambda t: (order.get(t[0], 9), t[1], t[2]))
    print("vault_lint: %d issue(s) in %s" % (len(issues), vault_dir))
    for kind, note, detail in issues:
        print("  [%-11s] %s -> %s" % (kind, note, detail))
    sys.stderr.write(
        "\nvault_lint FAILED: fix broken links / stale paths, or exclude "
        "template notes via engram.hooks.json (vault_lint.exclude_globs / "
        "orphan_exempt).\n")
    return 1


# --------------------------------------------------------------------------
def _selftest():
    import tempfile
    import shutil

    def build(d):
        os.makedirs(os.path.join(d, "sub"), exist_ok=True)
        # a real code file to satisfy a path check
        with open(os.path.join(d, "real_code.py"), "w", encoding="utf-8") as f:
            f.write("print('hi')\n")
        return d

    fails = []

    # ---- PASS fixture -----------------------------------------------------
    p = build(tempfile.mkdtemp(prefix="vlint_pass_"))
    with open(os.path.join(p, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Index\nsee [[note-a]] and [[note-b]]\n")
    with open(os.path.join(p, "note-a.md"), "w", encoding="utf-8") as f:
        f.write("A links to [[note-b]] and file `real_code.py`... "
                "no wait, `sub/note-b` link.\n")
    with open(os.path.join(p, "sub", "note-b.md"), "w", encoding="utf-8") as f:
        # UTF-8 trap: smart quotes / em dash that would break under CP1252 write
        f.write("B — “smart” note. Back to [[note-a]].\n")
    rc = run(p)
    if rc != 0:
        fails.append("PASS fixture returned %d (expected 0)" % rc)
    shutil.rmtree(p, ignore_errors=True)

    # ---- FAIL: broken wikilink -------------------------------------------
    p = build(tempfile.mkdtemp(prefix="vlint_broken_"))
    with open(os.path.join(p, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n[[note-a]] [[does-not-exist]]\n")
    with open(os.path.join(p, "note-a.md"), "w", encoding="utf-8") as f:
        f.write("[[index]]\n")
    issues = lint(p, dict(DEFAULTS))
    if not any(k == "broken-link" and d == "does-not-exist" for k, n, d in issues):
        fails.append("broken-link not detected: %r" % issues)
    if run(p) == 0:
        fails.append("broken-link fixture returned 0 (expected nonzero)")
    shutil.rmtree(p, ignore_errors=True)

    # ---- FAIL: orphan note -----------------------------------------------
    p = build(tempfile.mkdtemp(prefix="vlint_orphan_"))
    with open(os.path.join(p, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n[[linked]]\n")
    with open(os.path.join(p, "linked.md"), "w", encoding="utf-8") as f:
        f.write("I am linked. [[index]]\n")
    with open(os.path.join(p, "lonely.md"), "w", encoding="utf-8") as f:
        f.write("Nobody links to me.\n")
    issues = lint(p, dict(DEFAULTS))
    if not any(k == "orphan" and os.path.basename(n) == "lonely.md"
               for k, n, d in issues):
        fails.append("orphan not detected: %r" % issues)
    shutil.rmtree(p, ignore_errors=True)

    # ---- FAIL: stale backticked path -------------------------------------
    p = build(tempfile.mkdtemp(prefix="vlint_stale_"))
    with open(os.path.join(p, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n[[note-a]]\n")
    with open(os.path.join(p, "note-a.md"), "w", encoding="utf-8") as f:
        f.write("[[index]] good: `real_code.py` bad: `sub/ghost/missing.py`\n")
    issues = lint(p, dict(DEFAULTS))
    if not any(k == "stale-path" and "missing.py" in d for k, n, d in issues):
        fails.append("stale-path not detected: %r" % issues)
    if any(k == "stale-path" and "real_code.py" in d for k, n, d in issues):
        fails.append("real path wrongly flagged stale: %r" % issues)
    shutil.rmtree(p, ignore_errors=True)

    # ---- exclusions honored ----------------------------------------------
    p = build(tempfile.mkdtemp(prefix="vlint_excl_"))
    with open(os.path.join(p, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n[[linked]]\n")
    with open(os.path.join(p, "linked.md"), "w", encoding="utf-8") as f:
        f.write("[[index]]\n")
    with open(os.path.join(p, "0000-template.md"), "w", encoding="utf-8") as f:
        f.write("[[nonexistent-target]] and orphan-y content\n")
    issues = lint(p, dict(DEFAULTS))
    if any(n.endswith("0000-template.md") for k, n, d in issues):
        fails.append("excluded 0000 template still flagged: %r" % issues)
    shutil.rmtree(p, ignore_errors=True)

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("vault_lint --selftest: PASS "
          "(pass fixture + broken-link + orphan + stale-path + exclusions)")
    return 0


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    config = None
    if "--config" in argv:
        i = argv.index("--config")
        if i + 1 < len(argv):
            config = argv[i + 1]
            del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.stderr.write("usage: python vault_lint.py <vault_dir> "
                         "[--config file] | --selftest\n")
        return 2
    return run(args[0], config)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
