#!/usr/bin/env python3
"""upload_lint — heuristic guard check for file-upload / ingest handlers.

HEURISTIC, NOT SOUND. This detects handlers that look like they accept an
uploaded file, then checks each for the five hardening guards. It works by
pattern-matching over the function's AST/source, so it can miss a guard that is
implemented in an unusual way, and it can flag one as missing when it's just
spelled differently. Every result is FOR REVIEW, not a verdict.

Handler detection (heuristic): a function is treated as an upload/ingest handler
if its body references any of `request.FILES`, `UploadFile`, `multipart`,
`request.files`, `await request.form`, or `file: UploadFile` — configurable.

The five guards checked per handler:
  1. extension allowlist   — an allowlist of extensions is consulted
  2. size check BEFORE read — a size/length limit is checked before the file is
                              fully read into memory
  3. magic-byte sniff       — content is sniffed (magic bytes / libmagic / signature)
                              rather than trusting the extension
  4. parser wrapped -> 400  — the parse call is wrapped in try/except that returns
                              an HTTP 400 (not a 500 / uncaught exception)
  5. auth is separate       — an auth/permission check exists, distinct from the
                              upload validation

Marker lists for each guard are configurable via engram.hooks.json under the
`upload_lint` key; built-in defaults apply when config is absent.

Usage:
  python upload_lint.py <path> [<path> ...]   scan files/dirs
  python upload_lint.py --selftest            run built-in fixtures

Exit codes: 0 = every detected handler has all 5 guards (or no handlers found),
2 = at least one handler is missing a guard (advisory block),
1 = usage / internal error. Findings print to stderr.

Pure Python 3 stdlib (uses `ast`). Cross-platform.
"""
import ast
import json
import os
import sys

GUARDS = [
    "extension_allowlist",
    "size_before_read",
    "magic_sniff",
    "parser_wrapped_400",
    "auth_separate",
]

DEFAULTS = {
    # substrings (case-insensitive) that mark a function as an upload handler
    "handler_markers": [
        "request.files", "uploadfile", "multipart",
        "request.form", ".read()", "file.filename", "content_type",
    ],
    # stronger markers: presence of any one is sufficient on its own
    "handler_strong_markers": [
        "request.files", "uploadfile", "multipart",
    ],
    # per-guard detection markers (case-insensitive substrings)
    "guards": {
        "extension_allowlist": [
            "allowed_extensions", "allowlist", "whitelist", "valid_extensions",
            "splitext", ".endswith(", "allowed_ext", "extension in",
        ],
        "size_before_read": [
            "content_length", "max_size", "max_upload", "size >",
            "size >", "len(", "spool", "chunk", "file.size", "content-length",
            "size_limit", "too large", "413",
        ],
        "magic_sniff": [
            "magic", "sniff", "signature", "imghdr", "filetype",
            "b'\\x89png'", "b\"\\x89png\"", "startswith(b", "mime_from",
            "read(8)", "read(4)", "header_bytes", "magic_bytes",
        ],
        "parser_wrapped_400": [
            "400", "httpresponsebadrequest", "badrequest", "status=400",
            "status_code=400", "validationerror",
        ],
        "auth_separate": [
            "login_required", "permission", "is_authenticated", "request.user",
            "@login", "isauthenticated", "current_user", "require_auth",
            "authenticate", "depends(", "token", "authorized",
        ],
    },
}


def _load_config(start):
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start) or ".")
    for _ in range(40):
        for path in (
            os.path.join(d, "plugins", "engram", "hooks", "engram.hooks.json"),
            os.path.join(d, "engram.hooks.json"),
        ):
            if os.path.isfile(path):
                try:
                    raw = json.load(open(path, encoding="utf-8"))
                    sub = raw.get("upload_lint", {})
                    for k in ("handler_markers", "handler_strong_markers"):
                        if k in sub:
                            cfg[k] = sub[k]
                    if "guards" in sub:
                        for g in GUARDS:
                            if g in sub["guards"]:
                                cfg["guards"][g] = sub["guards"][g]
                    return cfg
                except Exception:
                    return cfg
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return cfg


def _fn_source(fn, lines):
    lo = fn.lineno - 1
    hi = getattr(fn, "end_lineno", fn.lineno)
    return "\n".join(lines[lo:hi])


def _decorator_source(fn, lines):
    out = []
    for dec in fn.decorator_list:
        lo = dec.lineno - 1
        hi = getattr(dec, "end_lineno", dec.lineno)
        out.append("\n".join(lines[lo:hi]))
    return "\n".join(out)


def _is_handler(fn_src, sig_src, cfg):
    hay = (fn_src + "\n" + sig_src).lower()
    if any(m.lower() in hay for m in cfg["handler_strong_markers"]):
        return True
    hits = sum(1 for m in cfg["handler_markers"] if m.lower() in hay)
    # weak markers alone are noisy; require .read() plus one file-ish cue
    if ".read()" in hay and hits >= 2:
        return True
    return False


def _has_marker(hay, markers):
    return any(m.lower() in hay for m in markers)


def _check_size_before_read(fn, lines, cfg):
    """Size guard must appear BEFORE the first full .read() with no size arg."""
    size_markers = cfg["guards"]["size_before_read"]
    first_full_read_line = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "read" and not node.args:
                ln = node.lineno
                if first_full_read_line is None or ln < first_full_read_line:
                    first_full_read_line = ln
    fn_lo = fn.lineno
    if first_full_read_line is None:
        # no unbounded full read seen; treat size guard as satisfied-by-absence
        # only if some size marker exists anywhere, else it's genuinely missing
        return _has_marker(_fn_source(fn, lines).lower(), size_markers)
    before = "\n".join(lines[fn_lo - 1:first_full_read_line - 1]).lower()
    return _has_marker(before, size_markers)


def scan_source(src, filename, cfg):
    lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    results = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_src = _fn_source(fn, lines)
        dec_src = _decorator_source(fn, lines)
        sig_src = dec_src
        if not _is_handler(fn_src, sig_src, cfg):
            continue
        hay = (fn_src + "\n" + dec_src).lower()
        present = {}
        for g in GUARDS:
            if g == "size_before_read":
                present[g] = _check_size_before_read(fn, lines, cfg)
            else:
                present[g] = _has_marker(hay, cfg["guards"][g])
        missing = [g for g in GUARDS if not present[g]]
        results.append({
            "func": fn.name,
            "line": fn.lineno,
            "present": present,
            "missing": missing,
        })
    return results


def _iter_py(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(root, f)
        elif p.endswith(".py"):
            yield p


def scan_paths(paths):
    cfg = _load_config(paths[0] if paths else ".")
    handlers = 0
    with_missing = 0
    for fp in _iter_py(paths):
        try:
            src = open(fp, encoding="utf-8").read()
        except Exception as e:
            print("  skip %s (%s)" % (fp, e), file=sys.stderr)
            continue
        for r in scan_source(src, fp, cfg):
            handlers += 1
            if r["missing"]:
                with_missing += 1
                print("\n%s" % fp, file=sys.stderr)
                print("  [review] L%d  %s: upload handler missing %d guard(s)"
                      % (r["line"], r["func"], len(r["missing"])), file=sys.stderr)
                for g in GUARDS:
                    mark = "ok " if r["present"][g] else "MISSING"
                    print("        [%s] %s" % (mark, g), file=sys.stderr)
    return handlers, with_missing


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print(__doc__, file=sys.stderr)
        return 1
    handlers, with_missing = scan_paths(paths)
    if handlers == 0:
        print("upload_lint: no upload/ingest handlers detected (heuristic).")
        return 0
    if with_missing == 0:
        print("upload_lint: %d handler(s) checked, all 5 guards present (heuristic)."
              % handlers)
        return 0
    print("\nupload_lint: %d of %d handler(s) missing >=1 guard — REVIEW, not proof."
          % (with_missing, handlers), file=sys.stderr)
    print("Hardening order: extension allowlist -> size cap BEFORE read -> "
          "magic-byte sniff -> wrap parser to 400 -> auth is separate.",
          file=sys.stderr)
    return 2


# --------------------------------------------------------------------------
def _selftest():
    import tempfile
    bad = '''
def upload_avatar(request):
    f = request.FILES["avatar"]
    data = f.read()
    img = parse_image(data)
    return save(img)
'''
    good = '''
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest

ALLOWED_EXTENSIONS = {".png", ".jpg"}

@login_required                                   # auth is separate
def upload_avatar(request):
    f = request.FILES["avatar"]
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:             # extension allowlist
        return HttpResponseBadRequest("bad ext")  # 400
    if f.size > MAX_SIZE:                          # size check BEFORE read
        return HttpResponseBadRequest("too large")
    head = f.read(8)                              # bounded read for sniff
    if not head.startswith(b"\\x89PNG"):           # magic-byte sniff
        return HttpResponseBadRequest("not png")
    try:
        img = parse_image(f.read())               # parser wrapped
    except Exception:
        return HttpResponseBadRequest("parse")    # -> 400
    return save(img)
'''
    unrelated = '''
def compute_total(items):
    return sum(i.price for i in items)
'''
    cfg = json.loads(json.dumps(DEFAULTS))
    rb = scan_source(bad, "bad.py", cfg)
    rg = scan_source(good, "good.py", cfg)
    ru = scan_source(unrelated, "unrelated.py", cfg)

    ok = True

    if len(rb) != 1:
        print("FAIL: bad file: expected 1 handler, got %d" % len(rb), file=sys.stderr); ok = False
    else:
        expect_missing = {"extension_allowlist", "size_before_read",
                          "magic_sniff", "parser_wrapped_400", "auth_separate"}
        got_missing = set(rb[0]["missing"])
        if not expect_missing.issubset(got_missing):
            print("FAIL: bad handler should be missing all 5 guards, got missing=%s"
                  % rb[0]["missing"], file=sys.stderr); ok = False
        else:
            print("PASS: bad handler flagged, missing all guards: %s" % rb[0]["missing"])

    if len(rg) != 1:
        print("FAIL: good file: expected 1 handler, got %d" % len(rg), file=sys.stderr); ok = False
    elif rg[0]["missing"]:
        print("FAIL: good handler reported missing guards: %s (present=%s)"
              % (rg[0]["missing"], rg[0]["present"]), file=sys.stderr); ok = False
    else:
        print("PASS: good handler clean, all 5 guards detected")

    if ru:
        print("FAIL: unrelated (non-upload) code detected as handler: %s" % ru,
              file=sys.stderr); ok = False
    else:
        print("PASS: unrelated non-upload code not treated as a handler")

    # end-to-end plumbing
    with tempfile.TemporaryDirectory() as d:
        bp = os.path.join(d, "bad.py")
        open(bp, "w", encoding="utf-8").write(bad)
        handlers, with_missing = scan_paths([bp])
        if with_missing < 1:
            print("FAIL: scan_paths did not surface the bad handler", file=sys.stderr); ok = False
        else:
            print("PASS: scan_paths surfaced the bad handler")

    print("\nSELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
