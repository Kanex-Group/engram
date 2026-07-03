#!/usr/bin/env python3
"""Atomic next-ID allocator for dev-spine indexes.

IDs are `<TYPE>_####` (zero-padded). The "next free" marker is a single line in
the index, by default of the shape:

    > Next free IDs — Sxn: 0001 · IS: 0001 · Fx: 0001 · FT: 0001

Allocation is atomic: read the marker → return the id → rewrite the bumped
marker in one guarded write. The table is NEVER scanned; the marker is the only
source of truth, so allocation stays O(1) and can't double-allocate.

  python brain-id.py next <TYPE> --index <file>    allocate + bump (prints id)
  python brain-id.py peek <TYPE> --index <file>     show next id, no bump

Options:
  --pad <n>            zero-pad width (default 4)
  --marker-re <regex>  regex locating the marker line (must capture nothing
                       special; the tool edits the `<TYPE>: ####` field in place)
  --field-re <regex>   regex for one `TYPE: ####` field; needs groups (type,num).
                       Default matches `Sxn: 0001` style fields.

Config: reads `hooks/engram.hooks.json` (key `"ids"`) if found next to the
tools dir or via --config; else built-in defaults. Pure Python 3 stdlib.

Exit 0 = ok. Non-zero = failure (missing marker, unknown type, etc.), with the
reason + a fix hint printed to stderr.
"""
import argparse
import json
import os
import re
import sys
import tempfile

# --- built-in defaults (public-safe, generic) --------------------------------
DEFAULTS = {
    # The marker line: a `> ` blockquote beginning with this literal prefix.
    "marker_prefix": "> Next free IDs",
    # One `TYPE: ####` field. Groups: (1) type token, (2) numeric id.
    # Fields are separated by `·` / `,` / whitespace in the wild; we only ever
    # rewrite the single field for the requested TYPE, in place.
    "field_re": r"([A-Za-z][A-Za-z0-9]*)\s*:\s*(\d+)",
    "pad": 4,
}


def _err(msg):
    sys.stderr.write("brain-id: " + msg + "\n")


def _load_config(explicit):
    """Merge built-in defaults with an optional engram.hooks.json `ids` block."""
    cfg = dict(DEFAULTS)
    paths = []
    if explicit:
        paths.append(explicit)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        # tools/ -> ../hooks/engram.hooks.json
        paths.append(os.path.join(here, os.pardir, "hooks", "engram.hooks.json"))
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            ids = data.get("ids") or {}
            for k in ("marker_prefix", "field_re", "pad"):
                if k in ids:
                    cfg[k] = ids[k]
            break
        except (OSError, ValueError):
            continue
    return cfg


def _find_marker(lines, prefix):
    """Return the index of the first line whose stripped text starts with the
    marker prefix, or None."""
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith(prefix):
            return i
    return None


def _read_field(marker_line, field_re, wanted_type):
    """Return (current_int, pad_width_seen, match) for `wanted_type` in the
    marker line, or (None, None, None) if that type isn't present."""
    for m in re.finditer(field_re, marker_line):
        typ, num = m.group(1), m.group(2)
        if typ == wanted_type:
            return int(num), len(num), m
    return None, None, None


def _atomic_write(path, text):
    """Write `text` to `path` atomically (temp file in same dir + os.replace)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def allocate(index_path, wanted_type, cfg, bump):
    """Core allocator. Returns the zero-padded id string. If `bump`, rewrites
    the marker atomically. Raises SystemExit-style errors via return of None
    plus a printed reason (caller maps to exit code)."""
    try:
        with open(index_path, encoding="utf-8", newline="") as f:
            raw = f.read()
    except OSError as e:
        _err("cannot read index %r: %s" % (index_path, e))
        _err("fix: pass an existing index file via --index.")
        return None

    # Preserve exact line endings by splitting but keeping them.
    lines = raw.splitlines(keepends=True)
    stripped = [ln.rstrip("\r\n") for ln in lines]

    mi = _find_marker(stripped, cfg["marker_prefix"])
    if mi is None:
        _err("no marker line found (expected a line starting with %r)."
             % cfg["marker_prefix"])
        _err("fix: add a marker line to %s, e.g.:" % index_path)
        _err("     %s — %s_0001" % (cfg["marker_prefix"], wanted_type))
        return None

    marker = stripped[mi]
    cur, seen_pad, m = _read_field(marker, cfg["field_re"], wanted_type)
    if cur is None:
        _err("type %r not present in the marker line." % wanted_type)
        _err("marker: %s" % marker.strip())
        _err("fix: add `%s: 0001` to the marker, or use a listed type."
             % wanted_type)
        return None

    pad = max(int(cfg["pad"]), seen_pad)
    alloc_id = "%s_%0*d" % (wanted_type, pad, cur)

    if not bump:
        return alloc_id

    nxt = cur + 1
    # Rewrite just the numeric group of the matched field, preserving the rest
    # of the field's surrounding text (label, spacing, separators).
    new_num = "%0*d" % (pad, nxt)
    new_marker = marker[:m.start(2)] + new_num + marker[m.end(2):]

    # Reattach the original line ending.
    orig = lines[mi]
    ending = orig[len(orig.rstrip("\r\n")):]
    lines[mi] = new_marker + ending

    _atomic_write(index_path, "".join(lines))
    return alloc_id


def main(argv):
    if "--selftest" in argv:
        return selftest()

    ap = argparse.ArgumentParser(prog="brain-id.py", add_help=True)
    ap.add_argument("cmd", choices=["next", "peek"],
                    help="next=allocate+bump, peek=show without bump")
    ap.add_argument("type", nargs="?", help="ID type token, e.g. Sxn / IS / Fx")
    ap.add_argument("--index", help="path to the index file holding the marker")
    ap.add_argument("--pad", type=int)
    ap.add_argument("--marker-prefix")
    ap.add_argument("--field-re")
    ap.add_argument("--config")
    args = ap.parse_args(argv)

    if not args.type or not args.index:
        _err("usage: brain-id.py %s <TYPE> --index <file>" % args.cmd)
        return 2

    cfg = _load_config(args.config)
    if args.pad is not None:
        cfg["pad"] = args.pad
    if args.marker_prefix is not None:
        cfg["marker_prefix"] = args.marker_prefix
    if args.field_re is not None:
        cfg["field_re"] = args.field_re

    alloc_id = allocate(args.index, args.type, cfg, bump=(args.cmd == "next"))
    if alloc_id is None:
        return 1
    sys.stdout.write(alloc_id + "\n")
    return 0


# --- self-test ---------------------------------------------------------------
def selftest():
    import shutil
    tmp = tempfile.mkdtemp(prefix="brainid_selftest_")
    ok = True

    def check(cond, label):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print("  [%s] %s" % (status, label))

    try:
        idx = os.path.join(tmp, "index.md")
        marker = "> Next free IDs — Sxn: 0007 · IS: 0012 · Fx: 0003 · FT: 0001"
        with open(idx, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Sessions\n\n" + marker + "\n\n| ID | x |\n|---|---|\n")

        cfg = dict(DEFAULTS)

        # peek does not bump
        p1 = allocate(idx, "Sxn", cfg, bump=False)
        p2 = allocate(idx, "Sxn", cfg, bump=False)
        check(p1 == "Sxn_0007", "peek returns zero-padded current id (%s)" % p1)
        check(p1 == p2, "peek is idempotent (no bump)")

        # next allocates then bumps
        a1 = allocate(idx, "Sxn", cfg, bump=True)
        a2 = allocate(idx, "Sxn", cfg, bump=True)
        a3 = allocate(idx, "Sxn", cfg, bump=True)
        check(a1 == "Sxn_0007", "first next == %s" % a1)
        check(a2 == "Sxn_0008", "second next == %s (bumped)" % a2)
        check(a3 == "Sxn_0009", "third next == %s (bumped)" % a3)
        check(len({a1, a2, a3}) == 3, "no double-allocate across sequential next")

        # marker actually rewritten on disk
        disk = open(idx, encoding="utf-8").read()
        check("Sxn: 0010" in disk, "marker bumped on disk to Sxn: 0010")
        # other types untouched
        check("IS: 0012" in disk and "Fx: 0003" in disk,
              "other types untouched")

        # a different type is independent
        b1 = allocate(idx, "IS", cfg, bump=True)
        check(b1 == "IS_0012", "independent type IS allocates %s" % b1)
        disk = open(idx, encoding="utf-8").read()
        check("IS: 0013" in disk, "IS marker bumped")
        check("Sxn: 0010" in disk, "Sxn unaffected by IS allocation")

        # atomicity: no leftover .tmp files in the dir
        leftovers = [x for x in os.listdir(tmp) if x.endswith(".tmp")]
        check(not leftovers, "no leftover temp files (atomic replace)")

        # missing marker => error (None)
        idx2 = os.path.join(tmp, "nomarker.md")
        with open(idx2, "w", encoding="utf-8") as f:
            f.write("# no marker here\n")
        r = allocate(idx2, "Sxn", cfg, bump=True)
        check(r is None, "missing marker handled gracefully (returns None)")

        # unknown type => error (None)
        r2 = allocate(idx, "ZZ", cfg, bump=False)
        check(r2 is None, "unknown type handled gracefully (returns None)")

        # padding respected via config
        idx3 = os.path.join(tmp, "pad6.md")
        with open(idx3, "w", encoding="utf-8", newline="\n") as f:
            f.write("> Next free IDs — QA: 000041\n")
        c6 = dict(DEFAULTS)
        c6["pad"] = 6
        a6 = allocate(idx3, "QA", c6, bump=True)
        check(a6 == "QA_000041", "6-wide padding honored (%s)" % a6)
        check("QA: 000042" in open(idx3, encoding="utf-8").read(),
              "6-wide marker bumped")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nbrain-id selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
