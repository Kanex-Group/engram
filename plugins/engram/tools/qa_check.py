#!/usr/bin/env python3
"""QA-record completeness parser — check EVIDENCE, not mere existence.

A merge-gate that only checks a QA record *exists* can be satisfied by an empty
stub. This tool parses the record and passes ONLY if it is actually complete:

  frontmatter `status: PASSED`  AND  zero remaining unticked applicable `- [ ]`.

Usage:
  python qa_check.py <QA_file.md>
      exit 0 iff COMPLETE; else print the unticked count + status and exit 1.

  python qa_check.py --find <dir> --branch <name>
      locate the matching QA_*.md for a branch and print its path (exit 0),
      else exit 1. Matches by branch token appearing in the filename or in the
      record's frontmatter `branch:` field.

Definitions:
  - frontmatter = a leading `---` ... `---` YAML-ish block (optional). `status:`
    is read from there if present, else from any top-level `status:` line.
  - PASSED = the configured passed_marker (default `status: PASSED`), matched
    case-insensitively on the status value.
  - unticked applicable box = a line matching `- [ ]`. A box is treated as
    NON-applicable (and ignored) if its text is struck (`~~...~~`) or tagged
    `(N/A)` / `n/a` — those never block.

Config: reads engram.hooks.json key `qa` for {dir, record_glob, passed_marker}.
Built-in defaults so it works with no config present. Pure stdlib, cross-platform.
"""
import os
import re
import sys
import json
import glob

DEFAULTS = {
    "dir": "QA",
    "record_glob": "QA_*.md",
    "passed_marker": "status: PASSED",
}

UNTICKED = re.compile(r"^\s*[-*]\s+\[\s\]\s*(.*)$")
TICKED = re.compile(r"^\s*[-*]\s+\[[xX]\]\s*(.*)$")
NA_RE = re.compile(r"(~~.*~~|\(n/?a\)|\bn/a\b)", re.IGNORECASE)


def _die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def _load_config(start):
    d = os.path.abspath(start)
    while True:
        for rel in ("engram.hooks.json",
                    os.path.join("hooks", "engram.hooks.json"),
                    os.path.join("plugins", "engram", "hooks", "engram.hooks.json")):
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return (json.load(f).get("qa") or {})
                except Exception:
                    return {}
        parent = os.path.dirname(d)
        if parent == d:
            return {}
        d = parent


def _cfg(start):
    c = dict(DEFAULTS)
    c.update(_load_config(start))
    return c


def _split_frontmatter(text):
    """Return (frontmatter_str, body_str). Frontmatter is a leading --- ... --- block."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return "", text


def _read_status(text, fm):
    """Read a status value from frontmatter first, else any top-level status: line."""
    for block in (fm, text):
        for line in block.splitlines():
            m = re.match(r"\s*status\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return None


def _fm_field(fm, field):
    for line in fm.splitlines():
        m = re.match(r"\s*%s\s*:\s*(.+?)\s*$" % re.escape(field), line, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("'\"")
    return None


def analyze(path, cfg):
    """Return (complete: bool, status: str|None, unticked: int, ticked: int)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm, _body = _split_frontmatter(text)
    status = _read_status(text, fm)

    unticked = 0
    ticked = 0
    for line in text.splitlines():
        m = UNTICKED.match(line)
        if m:
            if not NA_RE.search(m.group(1)):
                unticked += 1
            continue
        if TICKED.match(line):
            ticked += 1

    marker = cfg.get("passed_marker", DEFAULTS["passed_marker"])
    # passed_marker may be "status: PASSED" or just "PASSED"; compare the value.
    want = marker.split(":", 1)[1].strip() if ":" in marker else marker.strip()
    passed = bool(status) and status.strip().upper() == want.strip().upper()

    complete = passed and unticked == 0
    return complete, status, unticked, ticked


def cmd_check(path, cfg):
    if not os.path.isfile(path):
        _die("qa_check: file not found: %s" % path)
    complete, status, unticked, ticked = analyze(path, cfg)
    if complete:
        print("QA COMPLETE: %s (status=%s, %d/%d boxes ticked)"
              % (os.path.basename(path), status, ticked, ticked))
        return 0
    reasons = []
    if not status or status.strip().upper() != (
            cfg.get("passed_marker", "status: PASSED").split(":")[-1].strip().upper()):
        reasons.append("status=%s (need PASSED)" % (status or "<missing>"))
    if unticked > 0:
        reasons.append("%d unticked applicable box(es)" % unticked)
    sys.stderr.write(
        "QA INCOMPLETE: %s -> %s\n" % (os.path.basename(path), "; ".join(reasons)))
    sys.stderr.write(
        "  Fix: tick every applicable `- [ ]` and set frontmatter `status: PASSED`.\n")
    return 1


def cmd_find(directory, branch, cfg):
    if not os.path.isdir(directory):
        _die("qa_check --find: not a directory: %s" % directory)
    pat = cfg.get("record_glob", DEFAULTS["record_glob"])
    candidates = glob.glob(os.path.join(directory, "**", pat), recursive=True)
    token = branch.strip().lower()
    # slug the branch too (e.g. feature/foo-bar -> foo-bar variants)
    tail = token.rsplit("/", 1)[-1]

    matched = []
    for c in candidates:
        base = os.path.basename(c).lower()
        if token in base or tail in base:
            matched.append(c)
            continue
        # fall back to a `branch:` field in the record's frontmatter
        try:
            with open(c, encoding="utf-8") as f:
                fm, _ = _split_frontmatter(f.read())
            b = (_fm_field(fm, "branch") or "").lower()
            if b and (b == token or b == tail or token in b or tail in b):
                matched.append(c)
        except Exception:
            continue

    if not matched:
        sys.stderr.write(
            "qa_check --find: no %s matching branch %r under %s\n"
            % (pat, branch, directory))
        return 1
    # deterministic: newest by mtime first
    matched.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    print(matched[0])
    return 0


def _opt(argv, name):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        _die("%s needs a value." % name)
    return None


def selftest():
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="qacheck_")
    cfg = dict(DEFAULTS)
    ok = True
    try:
        qadir = os.path.join(tmp, "QA")
        os.makedirs(qadir)

        complete_rec = os.path.join(qadir, "QA_feature-login.md")
        with open(complete_rec, "w", encoding="utf-8") as f:
            f.write("---\nstatus: PASSED\nbranch: feature/login\n---\n"
                    "# QA\n- [x] tests green\n- [x] runs locally\n"
                    "- [ ] ~~mobile check~~ (not applicable)\n"
                    "- [ ] skip (N/A)\n")

        unticked_rec = os.path.join(qadir, "QA_bug-payout.md")
        with open(unticked_rec, "w", encoding="utf-8") as f:
            f.write("---\nstatus: PASSED\nbranch: bug/payout\n---\n"
                    "- [x] repro confirmed\n- [ ] regression test added\n")

        nostatus_rec = os.path.join(qadir, "QA_infra-parity.md")
        with open(nostatus_rec, "w", encoding="utf-8") as f:
            f.write("---\nbranch: infra/parity\n---\n- [x] done\n")

        draft_rec = os.path.join(qadir, "QA_docs-readme.md")
        with open(draft_rec, "w", encoding="utf-8") as f:
            f.write("---\nstatus: DRAFT\nbranch: docs/readme\n---\n- [x] done\n")

        # 1. complete record passes (N/A boxes ignored)
        assert cmd_check(complete_rec, cfg) == 0, "complete record must pass"

        # 2. unticked applicable box fails
        assert cmd_check(unticked_rec, cfg) == 1, "unticked box must fail"

        # 3. missing status fails
        assert cmd_check(nostatus_rec, cfg) == 1, "missing status must fail"

        # 4. non-PASSED status fails even with all boxes ticked
        assert cmd_check(draft_rec, cfg) == 1, "DRAFT status must fail"

        # 5. analyze counts N/A correctly (2 N/A ignored, 0 real unticked)
        comp, st, un, ti = analyze(complete_rec, cfg)
        assert comp and un == 0 and ti == 2, "N/A boxes must not count as unticked"

        # 6. --find locates by filename token
        assert cmd_find(qadir, "feature/login", cfg) == 0, "find by branch token"
        # 7. --find by frontmatter branch field
        assert cmd_find(qadir, "payout", cfg) == 0, "find by tail token"
        # 8. --find miss returns 1
        assert cmd_find(qadir, "nonexistent-branch", cfg) == 1, "find miss => 1"

        print("SELFTEST qa_check: PASS")
    except AssertionError as e:
        ok = False
        print("SELFTEST qa_check: FAIL -", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        sys.exit(selftest())
    cfg = _cfg(os.getcwd())

    if "--find" in argv:
        directory = _opt(argv, "--find")
        branch = _opt(argv, "--branch")
        if not directory or not branch:
            _die("usage: qa_check.py --find <dir> --branch <name>")
        sys.exit(cmd_find(directory, branch, cfg))

    # positional QA file
    pos = [a for a in argv if not a.startswith("--")]
    if not pos:
        _die("usage: qa_check.py <QA_file.md>   |   qa_check.py --find <dir> --branch <name>")
    sys.exit(cmd_check(pos[0], cfg))


if __name__ == "__main__":
    main(sys.argv[1:])
