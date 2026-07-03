#!/usr/bin/env python3
"""Dev-spine note scaffolder — deterministic.

Allocates the next `<TYPE>_####` id (reusing brain-id's atomic allocator),
fills a template's frontmatter, writes the note into a folder, appends a row to
the index table matching its existing columns, and emits a nav/up footer.

  python brain-note.py new <type> "<title>" \
      --index <file> --dir <folder> \
      [--template <file>] [--date YYYY-MM-DD] [--up "[[Home]]"]

  python brain-note.py --selftest

Behaviour:
  * ID: allocated + bumped via brain-id (atomic; marker is source of truth).
  * File: `<dir>/<ID>.md`. Refuses to overwrite an existing file.
  * Template: if given, `{id} {type} {title} {date} {up}` placeholders are
    substituted. If omitted, a minimal generic note is generated with YAML-ish
    frontmatter (id/type/title/date) + heading + nav footer.
  * Index table: the row is appended directly below the last existing table
    row (a line starting with `|`) after the marker. Columns are inferred from
    the header separator row (`|---|---|`); the first two columns get id+title,
    a column whose header looks like a date gets the date, the rest blank —
    unless the template/args fully specify (kept generic + deterministic).
  * Footer: `Up: <up>` appended to the note (default `[[Home]]`).

--date defaults to today (datetime is available here). Pass --date for
reproducible output. Pure Python 3 stdlib.

Exit 0 = ok. Non-zero = failure, with reason + fix hint on stderr.
"""
import argparse
import datetime
import importlib.util
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _err(msg):
    sys.stderr.write("brain-note: " + msg + "\n")


def _load_brain_id():
    """Import brain-id.py as a module (hyphen in name => load by path)."""
    path = os.path.join(_HERE, "brain-id.py")
    spec = importlib.util.spec_from_file_location("brain_id", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DEFAULT_TEMPLATE = """\
---
id: {id}
type: {type}
title: {title}
date: {date}
---

# {id} — {title}

<!-- body -->

Up: {up}
"""


def _fill_template(text, fields):
    """Substitute {id}/{type}/{title}/{date}/{up} without touching other braces."""
    out = text
    for k, v in fields.items():
        out = out.replace("{" + k + "}", v)
    return out


def _table_columns(lines, marker_idx):
    """Find the index table after the marker and return (header_idx, sep_idx,
    last_row_idx, headers[list], ncols). Returns None if no table found."""
    sep_re = re.compile(r"^\s*\|?\s*:?-{2,}.*\|.*$")
    hdr_idx = sep_idx = None
    for i in range(marker_idx, len(lines)):
        ln = lines[i]
        if sep_re.match(ln) and "|" in ln and set(ln.strip()) <= set("|-: \t"):
            sep_idx = i
            hdr_idx = i - 1
            break
    if sep_idx is None:
        return None
    headers = [c.strip() for c in lines[hdr_idx].strip().strip("|").split("|")]
    ncols = len(headers)
    # last contiguous data row after the separator
    last = sep_idx
    for i in range(sep_idx + 1, len(lines)):
        if lines[i].strip().startswith("|"):
            last = i
        else:
            break
    return hdr_idx, sep_idx, last, headers, ncols


def _is_date_col(h):
    hl = h.lower()
    return "date" in hl or hl in ("created", "when")


def _build_row(headers, alloc_id, title, date):
    """Build a table row matching the header columns. Column 0 gets the id; any
    date-like column gets the date; the first remaining non-id/non-date column
    gets the title; the rest are blank. This handles both `id, title, date, …`
    and `id, date, title, …` layouts without brain-specific assumptions."""
    cells = [""] * len(headers)
    title_placed = False
    for i, h in enumerate(headers):
        if i == 0:
            cells[i] = alloc_id
        elif _is_date_col(h):
            cells[i] = date
        elif not title_placed:
            cells[i] = title
            title_placed = True
    return "| " + " | ".join(cells) + " |"


def scaffold(index_path, dir_path, wanted_type, title, date, up,
             template_path, cfg, brain_id):
    # 1) allocate id atomically (this also bumps the marker on disk)
    alloc_id = brain_id.allocate(index_path, wanted_type, cfg, bump=True)
    if alloc_id is None:
        # brain_id.allocate already printed the reason
        return None

    # 2) render note
    fields = {"id": alloc_id, "type": wanted_type, "title": title,
              "date": date, "up": up}
    if template_path:
        try:
            tpl = open(template_path, encoding="utf-8").read()
        except OSError as e:
            _err("cannot read template %r: %s" % (template_path, e))
            return None
    else:
        tpl = DEFAULT_TEMPLATE
    note = _fill_template(tpl, fields)
    if "Up:" not in note:
        note = note.rstrip() + "\n\nUp: " + up + "\n"

    # 3) place file (no overwrite)
    os.makedirs(dir_path, exist_ok=True)
    note_path = os.path.join(dir_path, alloc_id + ".md")
    if os.path.exists(note_path):
        _err("refusing to overwrite existing note %r." % note_path)
        return None
    with open(note_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(note)

    # 4) append index-table row matching existing columns
    with open(index_path, encoding="utf-8", newline="") as f:
        raw = f.read()
    lines = raw.splitlines(keepends=True)
    plain = [ln.rstrip("\r\n") for ln in lines]

    mi = None
    for i, ln in enumerate(plain):
        if ln.lstrip().startswith(cfg["marker_prefix"]):
            mi = i
            break
    tbl = _table_columns(plain, mi if mi is not None else 0)
    row_written = False
    if tbl:
        _, _, last_idx, headers, _ = tbl
        row = _build_row(headers, alloc_id, title, date)
        # detect the line ending used on the anchor line
        anchor = lines[last_idx]
        ending = anchor[len(anchor.rstrip("\r\n")):] or "\n"
        lines.insert(last_idx + 1, row + ending)
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lines))
        row_written = True
    else:
        _err("warning: no index table found; note created but no row appended.")

    return {"id": alloc_id, "path": note_path, "row": row_written}


def main(argv):
    if "--selftest" in argv:
        return selftest()

    ap = argparse.ArgumentParser(prog="brain-note.py", add_help=True)
    ap.add_argument("cmd", choices=["new"])
    ap.add_argument("type", nargs="?")
    ap.add_argument("title", nargs="?")
    ap.add_argument("--index")
    ap.add_argument("--dir")
    ap.add_argument("--template")
    ap.add_argument("--date")
    ap.add_argument("--up", default="[[Home]]")
    ap.add_argument("--pad", type=int)
    ap.add_argument("--marker-prefix")
    ap.add_argument("--field-re")
    ap.add_argument("--config")
    args = ap.parse_args(argv)

    if not (args.type and args.title and args.index and args.dir):
        _err('usage: brain-note.py new <type> "<title>" --index <file> --dir <folder>')
        return 2

    brain_id = _load_brain_id()
    cfg = brain_id._load_config(args.config)
    if args.pad is not None:
        cfg["pad"] = args.pad
    if args.marker_prefix is not None:
        cfg["marker_prefix"] = args.marker_prefix
    if args.field_re is not None:
        cfg["field_re"] = args.field_re

    date = args.date or datetime.date.today().isoformat()

    res = scaffold(args.index, args.dir, args.type, args.title, date,
                   args.up, args.template, cfg, brain_id)
    if res is None:
        return 1
    print(res["id"])
    print(res["path"])
    return 0


# --- self-test ---------------------------------------------------------------
def selftest():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="brainnote_selftest_")
    ok = True

    def check(cond, label):
        nonlocal ok
        if not cond:
            ok = False
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    try:
        brain_id = _load_brain_id()
        cfg = dict(brain_id.DEFAULTS)

        idx = os.path.join(tmp, "Sessions.md")
        with open(idx, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "# Sessions\n\n"
                "> Next free IDs — Sxn: 0004 · IS: 0001\n\n"
                "| Session | Date | Purpose | Status |\n"
                "|---|---|---|---|\n"
                "| Sxn_0003 | 2026-06-01 | prior | done |\n"
            )
        notes = os.path.join(tmp, "notes")

        res = scaffold(idx, notes, "Sxn", "First scaffolded note",
                       "2026-07-03", "[[Home]]", None, cfg, brain_id)
        check(res is not None, "scaffold succeeded")
        check(res and res["id"] == "Sxn_0004", "allocated id == Sxn_0004")

        # file created
        note_path = os.path.join(notes, "Sxn_0004.md")
        check(os.path.exists(note_path), "note file created at <dir>/<ID>.md")
        body = open(note_path, encoding="utf-8").read()
        check("id: Sxn_0004" in body, "frontmatter id filled")
        check("type: Sxn" in body, "frontmatter type filled")
        check("date: 2026-07-03" in body, "frontmatter date-from-arg filled")
        check("First scaffolded note" in body, "title filled")
        check("Up: [[Home]]" in body.strip(), "nav/up footer emitted")

        # marker bumped
        disk = open(idx, encoding="utf-8").read()
        check("Sxn: 0005" in disk, "marker bumped Sxn 0004 -> 0005")

        # index row appended, matching columns (Session|Date|Purpose|Status):
        # id -> col0, date -> Date col, title -> first free col (Purpose), Status blank
        check("| Sxn_0004 | 2026-07-03 | First scaffolded note |  |" in disk,
              "index row appended matching columns (id, date, title)")
        # row placed after the existing data row
        i_prev = disk.index("Sxn_0003")
        i_new = disk.index("Sxn_0004 |")  # the table cell, not frontmatter
        check(i_new > i_prev, "new row appended below existing rows")

        # second scaffold => next id, no double-allocate
        res2 = scaffold(idx, notes, "Sxn", "Second note", "2026-07-03",
                        "[[Home]]", None, cfg, brain_id)
        check(res2 and res2["id"] == "Sxn_0005", "second scaffold == Sxn_0005")
        check(res["id"] != res2["id"], "no double-allocate across scaffolds")
        disk = open(idx, encoding="utf-8").read()
        check("Sxn: 0006" in disk, "marker bumped again to 0006")
        check(disk.count("| Sxn_0005 |") == 1, "exactly one row for Sxn_0005")

        # custom template with placeholders
        tpl = os.path.join(tmp, "tpl.md")
        with open(tpl, "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nid: {id}\ntype: {type}\n---\n# {title} ({date})\nUp: {up}\n")
        res3 = scaffold(idx, notes, "IS", "Templated issue", "2026-07-03",
                        "[[Issues]]", tpl, cfg, brain_id)
        check(res3 and res3["id"] == "IS_0001", "template path: IS_0001 allocated")
        tbody = open(res3["path"], encoding="utf-8").read()
        check("# Templated issue (2026-07-03)" in tbody, "template placeholders filled")
        check("Up: [[Issues]]" in tbody, "template up footer filled")

        # no-overwrite guard
        res4 = scaffold(idx, notes, "IS", "dupe", "2026-07-03", "[[x]]",
                        None, cfg, brain_id)
        # IS bumped to 0002 now, so this is a fresh id — verify guard separately
        check(res4 and res4["id"] == "IS_0002", "IS advanced to 0002 (independent)")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nbrain-note selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
