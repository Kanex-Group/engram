#!/usr/bin/env python3
"""Repeat-offender ledger — append-only record of recurring failures.

A bug that comes back is not the same bug: it's a *repeat offender*, and it must
be classified and gated, not silently re-fixed. This CLI keeps an append-only
ledger of offender signatures so a merge-gate can detect a recurrence and react.

  python offender_ledger.py add "<signature>" --class a --fix Fx_0007 [--fuse "..."]
  python offender_ledger.py check "<signature-or-area>"   # exit != 0 if seen before
  python offender_ledger.py list

Classes (repeat-offender decision tree):
  a  code root cause not yet fixed (e.g. parallel-path drift) -> NOT done, fix all paths
  b  scale/milestone-gated -> defer ONLY with a concrete fuse + ticket
  c  design-level -> schedule

Storage: append-only JSON-lines. Default path .engram/offenders.jsonl (override
with --file or config key offender_ledger.file). Past rows are NEVER mutated;
`add` only appends. Each row carries a stable SHA-256 hash of the normalized
signature so `check` can match by hash or by substring/area.

Pure Python 3 stdlib. Cross-platform.
"""
import os
import sys
import json
import time
import hashlib

CLASSES = {
    "a": "code-root-cause-not-yet-fixed",
    "b": "scale/milestone-gated",
    "c": "design-level",
}
DEFAULT_FILE = os.path.join(".engram", "offenders.jsonl")


def _die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def _norm(sig):
    """Normalize a signature so cosmetically-different spellings hash equal."""
    return " ".join((sig or "").lower().split())


def _sig_hash(sig):
    return hashlib.sha256(_norm(sig).encode("utf-8")).hexdigest()[:16]


def _load_config(start):
    """Best-effort read of engram.hooks.json walking up from start. Never raises."""
    d = os.path.abspath(start)
    while True:
        for rel in ("engram.hooks.json",
                    os.path.join("hooks", "engram.hooks.json"),
                    os.path.join("plugins", "engram", "hooks", "engram.hooks.json")):
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    return {}
        parent = os.path.dirname(d)
        if parent == d:
            return {}
        d = parent


def _resolve_file(argv, cfg):
    if "--file" in argv:
        i = argv.index("--file")
        if i + 1 < len(argv):
            return argv[i + 1]
        _die("--file needs a path.")
    return (cfg.get("offender_ledger", {}) or {}).get("file", DEFAULT_FILE)


def _read_rows(path):
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                # tolerate a corrupt line rather than crash the gate
                continue
    return rows


def _append_row(path, row):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    # append-only: open in 'a', never rewrite existing content
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _opt(argv, name):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        _die("%s needs a value." % name)
    return None


def cmd_add(argv, path):
    # positional signature = first arg that isn't a flag/flag-value
    flags = {"--class", "--fix", "--fuse", "--file"}
    sig = None
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
        sig = a
        break
    if not sig:
        _die("add: missing <signature>.\n"
             "  usage: offender_ledger.py add \"<signature>\" --class a|b|c --fix <Fx_id> [--fuse \"...\"]")

    klass = _opt(argv, "--class")
    if not klass or klass.lower() not in CLASSES:
        _die("add: --class must be one of a|b|c (got %r).\n"
             "  a=code-root-cause  b=scale/milestone-gated  c=design-level" % klass)
    klass = klass.lower()

    fix = _opt(argv, "--fix")
    if not fix:
        _die("add: --fix <Fx_id> is required (the fix that was supposed to close this).")
    fuse = _opt(argv, "--fuse")

    row = {
        "sig": sig,
        "hash": _sig_hash(sig),
        "class": klass,
        "class_desc": CLASSES[klass],
        "fix": fix,
        "fuse": fuse,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _append_row(path, row)
    print("Appended offender %s [class %s] fix=%s -> %s"
          % (row["hash"], klass, fix, path))
    return 0


def cmd_check(argv, path):
    flags = {"--file"}
    query = None
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
        query = a
        break
    if not query:
        _die("check: missing <signature-or-area>.\n"
             "  usage: offender_ledger.py check \"<signature-or-area>\"")

    rows = _read_rows(path)
    qhash = _sig_hash(query)
    qnorm = _norm(query)
    hits = []
    for r in rows:
        rsig = _norm(r.get("sig", ""))
        # match if: exact-hash equal, OR either string contains the other (area match)
        if r.get("hash") == qhash or (qnorm and (qnorm in rsig or rsig in qnorm)):
            hits.append(r)

    if not hits:
        print("No prior occurrence for %r (hash %s). OK." % (query, qhash))
        return 0

    last = hits[-1]
    sys.stderr.write(
        "RECURRENCE: %d prior occurrence(s) for %r.\n" % (len(hits), query))
    for r in hits:
        sys.stderr.write("  - %s [class %s: %s] fix=%s fuse=%s (%s)\n" % (
            r.get("hash"), r.get("class"), r.get("class_desc"),
            r.get("fix"), (r.get("fuse") or "-"), r.get("ts")))
    sys.stderr.write(
        "  Last verdict: class %s (%s); fuse: %s\n" % (
            last.get("class"), last.get("class_desc"), last.get("fuse") or "-"))
    sys.stderr.write(
        "  Fix: classify per repeat-offender tree. class a => NOT done, fix ALL paths.\n")
    return 1


def cmd_list(path):
    rows = _read_rows(path)
    if not rows:
        print("(ledger empty: %s)" % path)
        return 0
    print("=== Offender ledger: %d record(s) [%s] ===" % (len(rows), path))
    for r in rows:
        print("  %s  class %s  fix=%s  %s  | %s" % (
            r.get("hash"), r.get("class"), r.get("fix"),
            r.get("ts"), r.get("sig")))
        if r.get("fuse"):
            print("        fuse: %s" % r["fuse"])
    return 0


def selftest():
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="offledger_")
    ok = True
    try:
        path = os.path.join(tmp, "sub", "offenders.jsonl")

        # 1. add appends a row
        rc = cmd_add(["double payout on retry", "--class", "a",
                      "--fix", "Fx_0007"], path)
        assert rc == 0, "add should return 0"
        assert os.path.isfile(path), "ledger file created"
        assert len(_read_rows(path)) == 1, "one row after first add"

        # 2. check on a NEW signature => 0 (no recurrence)
        rc = cmd_check(["totally unrelated thing"], path)
        assert rc == 0, "unseen signature must pass (exit 0)"

        # 3. check on the SAME signature => nonzero (recurrence detected)
        rc = cmd_check(["double payout on retry"], path)
        assert rc == 1, "exact recurrence must fail (exit nonzero)"

        # 4. check by AREA substring => nonzero
        rc = cmd_check(["payout"], path)
        assert rc == 1, "area substring recurrence must fail"

        # 5. add second row + fuse, confirm append-only (no mutation)
        before = open(path, encoding="utf-8").read()
        rc = cmd_add(["stale-branch reverts fix", "--class", "b",
                      "--fix", "Fx_0009", "--fuse", "gate at 500 users"], path)
        assert rc == 0
        after = open(path, encoding="utf-8").read()
        assert after.startswith(before), "append-only: old bytes unchanged"
        assert len(_read_rows(path)) == 2, "two rows now"

        # 6. stable hash: same signature => same hash across normalization
        assert _sig_hash("Double Payout On Retry") == _sig_hash(
            "double payout   on retry"), "hash must be normalization-stable"

        # 7. bad class rejected
        try:
            cmd_add(["x", "--class", "z", "--fix", "Fx_1"], path)
            ok = False
            print("FAIL: bad --class should have exited")
        except SystemExit as e:
            assert e.code != 0

        print("SELFTEST offender_ledger: PASS")
    except AssertionError as e:
        ok = False
        print("SELFTEST offender_ledger: FAIL -", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        sys.exit(selftest())
    if not argv:
        _die(__doc__)
    cmd = argv[0]
    rest = argv[1:]
    cfg = _load_config(os.getcwd())
    path = _resolve_file(rest, cfg)

    if cmd == "add":
        sys.exit(cmd_add(rest, path))
    elif cmd == "check":
        sys.exit(cmd_check(rest, path))
    elif cmd == "list":
        sys.exit(cmd_list(path))
    else:
        _die("Unknown command %r. Use: add | check | list | --selftest" % cmd)


if __name__ == "__main__":
    main(sys.argv[1:])
