#!/usr/bin/env python3
"""Deploy smoke test — a 200 can be an empty table.

Fetch a URL and assert its RESPONSE BODY is real, not merely that the request
returned HTTP 200. A page that loads with an empty grid, a missing list, or a
"no data" placeholder is still a broken deploy — status codes don't catch that.
So this asserts CONTENT: non-empty body, plus (optionally) that it contains a
given substring and/or repeats a row-like element at least N times.

Usage:
  python deploy_smoke.py <url> [--expect-selector CSS] [--min-rows N]
                               [--contains TEXT] [--timeout SECONDS]

  --contains TEXT        body must contain this literal substring.
  --expect-selector CSS  a coarse CSS selector whose matches are counted in the
                         raw HTML (tag, .class, #id, [attr], tag.class combos).
                         Used together with --min-rows to assert "enough rows".
                         With no --min-rows, at least ONE match is required.
  --min-rows N           require >= N matches of --expect-selector (default 1
                         when a selector is given). "A 200 with zero rows fails."
  --timeout SECONDS      fetch timeout (default 15).

Exit 0 iff every given assertion holds. Any content failure, or a network
error, exits non-zero with WHY + how to fix on stderr.

Config: reads engram.hooks.json key `deploy_smoke` for defaults
{timeout, user_agent}. Built-in defaults so it works with no config present.
`--selftest` uses local file:// fixtures ONLY — it never touches the network.

Pure Python 3 stdlib, cross-platform.
"""
import os
import re
import sys
import json
import urllib.request
import urllib.error

DEFAULTS = {
    "timeout": 15,
    "user_agent": "engram-deploy-smoke/1",
}


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
                        return (json.load(f).get("deploy_smoke") or {})
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


def fetch(url, timeout, user_agent):
    """Return (status, body_text). Raises urllib errors for the caller to catch.

    file:// URLs are supported (no headers) so self-tests need no network.
    """
    if url.startswith("file:"):
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
        return 200, raw.decode("utf-8", "replace")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", None) or resp.getcode()
        raw = resp.read()
    charset = "utf-8"
    try:
        ct = resp.headers.get_content_charset()
        if ct:
            charset = ct
    except Exception:
        pass
    return status, raw.decode(charset, "replace")


def _selector_to_regex(selector):
    """Translate a coarse CSS selector into a regex that counts opening tags.

    Supports: `tag`, `.class`, `#id`, `[attr]`, and `tag.class`. This is a
    deliberately shallow HTML-shape counter (stdlib only, no real parser) — it
    counts opening tags whose attributes satisfy the selector. Good enough to
    answer "are there >= N row-like elements".
    """
    sel = selector.strip()
    tag = r"[a-zA-Z][\w-]*"
    m = re.match(r"^(%s)?(?:\.([\w-]+))?(?:#([\w-]+))?(?:\[([\w-]+)\])?$" % tag, sel)
    if not m or not any(m.groups()):
        # Fall back: escape and count literal occurrences.
        return re.compile(re.escape(sel))
    g_tag, g_cls, g_id, g_attr = m.groups()
    tagpart = g_tag if g_tag else tag
    pat = r"<" + tagpart + r"\b"
    conds = []
    if g_cls:
        conds.append(r'class\s*=\s*["\'][^"\']*\b' + re.escape(g_cls) + r'\b')
    if g_id:
        conds.append(r'id\s*=\s*["\']' + re.escape(g_id) + r'["\']')
    if g_attr:
        conds.append(re.escape(g_attr) + r'\s*=')
    for c in conds:
        # attributes may appear in any order after the tag, before the '>'
        pat += r"(?=[^>]*" + c + r")"
    return re.compile(pat, re.IGNORECASE)


def count_matches(body, selector):
    return len(_selector_to_regex(selector).findall(body))


def check(url, cfg, contains=None, selector=None, min_rows=None):
    """Run assertions. Return (ok: bool, message: str)."""
    try:
        status, body = fetch(url, cfg["timeout"], cfg["user_agent"])
    except urllib.error.HTTPError as e:
        return False, "HTTP %s from %s (server returned an error status)" % (e.code, url)
    except urllib.error.URLError as e:
        return False, "network error fetching %s: %s" % (url, e.reason)
    except Exception as e:  # DNS, timeout, malformed URL, file-not-found ...
        return False, "could not fetch %s: %s" % (url, e)

    body = body or ""
    if not body.strip():
        return False, ("empty body from %s (HTTP %s). A 200 with no content is a "
                       "broken deploy." % (url, status))

    if contains is not None and contains not in body:
        return False, ("body from %s does not contain expected text %r "
                       "(status %s, %d bytes)." % (url, contains, status, len(body)))

    if selector is not None:
        need = min_rows if min_rows is not None else 1
        got = count_matches(body, selector)
        if got < need:
            return False, ("selector %r matched %d element(s) in %s; need >= %d. "
                           "A 200 with too few rows is still a broken table."
                           % (selector, got, url, need))
        return True, ("OK %s (HTTP %s, %d bytes, selector %r x%d >= %d)"
                      % (url, status, len(body), selector, got, need))

    if min_rows is not None:
        return False, "--min-rows requires --expect-selector to count against."

    return True, "OK %s (HTTP %s, %d bytes non-empty)" % (url, status, len(body))


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
    tmp = tempfile.mkdtemp(prefix="deploysmoke_")
    cfg = dict(DEFAULTS)
    ok = True

    def as_url(path):
        return "file:///" + os.path.abspath(path).replace(os.sep, "/").lstrip("/")

    try:
        good = os.path.join(tmp, "good.html")
        with open(good, "w", encoding="utf-8") as f:
            f.write("<html><body><table>"
                    '<tr class="row">a</tr>'
                    '<tr class="row">b</tr>'
                    '<tr class="row">c</tr>'
                    "</table><p>Dashboard ready</p></body></html>")

        empty_table = os.path.join(tmp, "empty.html")
        with open(empty_table, "w", encoding="utf-8") as f:
            f.write("<html><body><table></table>"
                    "<p>No records found</p></body></html>")

        blank = os.path.join(tmp, "blank.html")
        with open(blank, "w", encoding="utf-8") as f:
            f.write("   \n  \t\n")

        gurl, eurl, burl = as_url(good), as_url(empty_table), as_url(blank)

        # 1. non-empty body passes with no assertions
        assert check(gurl, cfg)[0] is True, "non-empty body should pass"

        # 2. blank body fails (the core "200 can be empty" case)
        assert check(blank and burl, cfg)[0] is False, "blank body must fail"

        # 3. --contains present passes
        assert check(gurl, cfg, contains="Dashboard ready")[0] is True, \
            "contains present should pass"

        # 4. --contains absent fails
        assert check(gurl, cfg, contains="Totally Missing")[0] is False, \
            "contains absent must fail"

        # 5. selector with enough rows passes
        assert check(gurl, cfg, selector="tr.row", min_rows=3)[0] is True, \
            "3 rows >= 3 should pass"

        # 6. selector demanding too many rows fails
        assert check(gurl, cfg, selector="tr.row", min_rows=4)[0] is False, \
            "4 required but only 3 present must fail"

        # 7. THE headline case: HTTP 200 but empty table -> zero rows -> fail
        assert check(eurl, cfg, selector="tr.row", min_rows=1)[0] is False, \
            "empty table (200) must fail the row assertion"

        # 8. bare tag selector counts
        assert count_matches(open(good, encoding="utf-8").read(), "tr") == 3, \
            "bare tag count"

        # 9. missing file / bad URL -> graceful failure, not crash
        assert check(as_url(os.path.join(tmp, "nope.html")), cfg)[0] is False, \
            "missing fixture must fail gracefully"

        # 10. --min-rows without selector is a usage failure
        assert check(gurl, cfg, min_rows=2)[0] is False, \
            "min-rows without selector must fail"

        print("SELFTEST deploy_smoke: PASS")
    except AssertionError as e:
        ok = False
        print("SELFTEST deploy_smoke: FAIL -", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        sys.exit(selftest())

    cfg = _cfg(os.getcwd())
    contains = _opt(argv, "--contains")
    selector = _opt(argv, "--expect-selector")
    min_rows_s = _opt(argv, "--min-rows")
    timeout_s = _opt(argv, "--timeout")
    if timeout_s is not None:
        try:
            cfg["timeout"] = float(timeout_s)
        except ValueError:
            _die("--timeout must be a number.")
    min_rows = None
    if min_rows_s is not None:
        try:
            min_rows = int(min_rows_s)
        except ValueError:
            _die("--min-rows must be an integer.")

    flags = {"--contains", "--expect-selector", "--min-rows", "--timeout"}
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
        _die("usage: deploy_smoke.py <url> [--expect-selector CSS] "
             "[--min-rows N] [--contains TEXT] [--timeout SECONDS]")

    ok, msg = check(pos[0], cfg, contains=contains, selector=selector,
                    min_rows=min_rows)
    if ok:
        print(msg)
        sys.exit(0)
    sys.stderr.write("DEPLOY SMOKE FAIL: " + msg + "\n")
    sys.stderr.write("  Fix: confirm the deploy actually rendered content "
                     "(not just returned 200); check data source / build.\n")
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
