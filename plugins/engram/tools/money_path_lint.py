#!/usr/bin/env python3
"""money_path_lint — heuristic scan for unlocked money paths.

HEURISTIC, NOT SOUND. This flags likely-risky patterns for HUMAN REVIEW; it
does not prove a bug and it will both miss real ones and flag safe code. Treat
every finding as "look here", never as "this is definitely broken".

What it looks for, in Python files that touch money/ledger/wallet symbols:
  - a balance-MUTATING write (e.g. `x.balance = ...`, `x.balance += ...`,
    a `.save()` on a wallet-ish object, or a call to credit/debit/...) that is
    NOT lexically inside a `transaction.atomic()` block, AND/OR
  - a money-object read in that same function that is NOT preceded by a
    `select_for_update()` (missing row lock -> lost-update / double-spend risk).
It also emits a reminder to add a conservation test:
    balance_before + amount == balance_after

Symbol lists (money symbols, mutating attrs, mutating calls, the atomic marker,
the lock marker) are configurable via engram.hooks.json under the
`money_path_lint` key; built-in defaults apply when config is absent.

Usage:
  python money_path_lint.py <path> [<path> ...]   scan files/dirs
  python money_path_lint.py --selftest            run built-in fixtures

Exit codes: 0 = no findings, 2 = at least one finding (advisory block),
1 = usage / internal error. Findings print to stderr; a clean run is silent
except for a short summary on stdout.

Pure Python 3 stdlib (uses `ast`). Cross-platform.
"""
import ast
import json
import os
import sys

# ---- built-in defaults (overridable via engram.hooks.json) ----------------
DEFAULTS = {
    # substrings that mark a name/attribute as "money-ish" (case-insensitive)
    "money_symbols": [
        "balance", "wallet", "ledger", "payout", "credit", "debit",
        "amount", "funds", "account_balance", "escrow", "settlement",
    ],
    # attribute assignments that MUTATE a balance (matched on the attr name)
    "mutating_attrs": ["balance", "funds", "amount", "escrow"],
    # method/function calls that mutate money state (matched on the func name)
    "mutating_calls": [
        "save", "update", "credit", "debit", "deposit", "withdraw",
        "transfer", "adjust_balance", "add_funds", "deduct",
    ],
    # how an atomic transaction block is opened (substring of the call source)
    "atomic_markers": ["transaction.atomic", "atomic("],
    # how a row lock is taken before the read (substring of the call source)
    "lock_markers": ["select_for_update"],
}

REVIEW = "[review]"  # every finding is advisory, label it as such


def _load_config(start):
    """Best-effort read of money_path_lint.* from engram.hooks.json; defaults on miss."""
    cfg = dict(DEFAULTS)
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start) or ".")
    for _ in range(40):
        cand = os.path.join(d, "plugins", "engram", "hooks", "engram.hooks.json")
        alt = os.path.join(d, "engram.hooks.json")
        for path in (cand, alt):
            if os.path.isfile(path):
                try:
                    raw = json.load(open(path, encoding="utf-8"))
                    sub = raw.get("money_path_lint", {})
                    for k in DEFAULTS:
                        if k in sub:
                            cfg[k] = sub[k]
                    return cfg
                except Exception:
                    return cfg
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return cfg


def _is_money_name(name, symbols):
    n = (name or "").lower()
    return any(s in n for s in symbols)


def _src_of(node, lines):
    """Best-effort source text for a node (single line is enough for markers)."""
    try:
        lo = node.lineno - 1
        hi = getattr(node, "end_lineno", node.lineno)
        return "\n".join(lines[lo:hi])
    except Exception:
        return ""


def _call_name(node):
    """Return the trailing attribute/func name of a Call, or ''."""
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


class _FuncScan:
    """Analyze one function body for money mutations + lock/atomic context."""

    def __init__(self, fn, lines, cfg):
        self.fn = fn
        self.lines = lines
        self.cfg = cfg
        self.findings = []

    def _under_atomic(self, node):
        """Is `node` lexically inside a `with transaction.atomic():` block?"""
        # We annotate atomic With-nodes and mark their descendants; simpler:
        return getattr(node, "_engram_atomic", False)

    def _has_lock_in_fn(self):
        markers = self.cfg["lock_markers"]
        for n in ast.walk(self.fn):
            if isinstance(n, ast.Call):
                src = _src_of(n, self.lines)
                if any(m in src for m in markers):
                    return True
        return False

    def run(self):
        cfg = self.cfg
        atomic_markers = cfg["atomic_markers"]

        # Mark descendants of atomic `with` blocks.
        for node in ast.walk(self.fn):
            if isinstance(node, ast.With):
                src = _src_of(node, self.lines)
                head = src.splitlines()[0] if src else ""
                if any(m in head for m in atomic_markers):
                    for d in ast.walk(node):
                        d._engram_atomic = True

        has_lock = self._has_lock_in_fn()
        touches_money = False
        mutations = []  # (lineno, desc, node)

        for node in ast.walk(self.fn):
            # attribute assignment: x.balance = / += ...
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Attribute) and t.attr.lower() in [
                        a.lower() for a in cfg["mutating_attrs"]
                    ]:
                        touches_money = True
                        mutations.append((node.lineno, "writes .%s" % t.attr, node))
            # mutating call: wallet.save(), credit(...), etc.
            if isinstance(node, ast.Call):
                cname = _call_name(node)
                if cname and cname.lower() in [c.lower() for c in cfg["mutating_calls"]]:
                    # only count save/update if the receiver looks money-ish,
                    # to cut noise; credit/debit-style names always count.
                    receiver_money = False
                    if isinstance(node.func, ast.Attribute):
                        recv = node.func.value
                        rname = ""
                        if isinstance(recv, ast.Name):
                            rname = recv.id
                        elif isinstance(recv, ast.Attribute):
                            rname = recv.attr
                        receiver_money = _is_money_name(rname, cfg["money_symbols"])
                    generic = cname.lower() in ("save", "update")
                    if generic and not receiver_money:
                        continue
                    touches_money = True
                    mutations.append((node.lineno, "calls %s()" % cname, node))
                # money read reference anywhere
            if isinstance(node, ast.Attribute) and _is_money_name(node.attr, cfg["money_symbols"]):
                touches_money = True
            if isinstance(node, ast.Name) and _is_money_name(node.id, cfg["money_symbols"]):
                touches_money = True

        if not mutations:
            return self.findings

        for lineno, desc, node in mutations:
            in_atomic = self._under_atomic(node)
            problems = []
            if not in_atomic:
                problems.append("not inside transaction.atomic()")
            if not has_lock:
                problems.append("no select_for_update() lock on the read")
            if problems:
                self.findings.append({
                    "func": self.fn.name,
                    "line": lineno,
                    "desc": desc,
                    "problems": problems,
                })
        return self.findings


def scan_source(src, filename, cfg):
    lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError as e:
        return [{"func": "<module>", "line": e.lineno or 0,
                 "desc": "could not parse (%s)" % e.msg, "problems": ["syntax error"],
                 "parse_error": True}]
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.extend(_FuncScan(node, lines, cfg).run())
    return out


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
    total = 0
    files_with = 0
    for fp in _iter_py(paths):
        try:
            src = open(fp, encoding="utf-8").read()
        except Exception as e:
            print("  skip %s (%s)" % (fp, e), file=sys.stderr)
            continue
        findings = scan_source(src, fp, cfg)
        # ignore parse errors on unrelated files silently unless they touch money
        real = [f for f in findings if not f.get("parse_error")]
        if not real:
            continue
        files_with += 1
        print("\n%s" % fp, file=sys.stderr)
        for f in real:
            total += 1
            print("  %s L%d  %s: %s" % (
                REVIEW, f["line"], f["func"], f["desc"]), file=sys.stderr)
            for p in f["problems"]:
                print("        - %s" % p, file=sys.stderr)
            print("        - REMINDER: add a conservation test: "
                  "balance_before + amount == balance_after", file=sys.stderr)
    return total, files_with


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print(__doc__, file=sys.stderr)
        return 1
    total, files_with = scan_paths(paths)
    if total == 0:
        print("money_path_lint: no likely-unlocked money paths found (heuristic).")
        return 0
    print("\nmoney_path_lint: %d finding(s) across %d file(s) — REVIEW, not proof."
          % (total, files_with), file=sys.stderr)
    print("These are heuristic. Confirm each by hand; wrap balance mutations in\n"
          "transaction.atomic() + select_for_update() and add a conservation test.",
          file=sys.stderr)
    return 2


# --------------------------------------------------------------------------
def _selftest():
    import tempfile
    bad = '''
from django.db import transaction

def apply_payout(wallet, amount):
    # no atomic, no lock -> should be flagged
    wallet.balance = wallet.balance + amount
    wallet.save()
'''
    good = '''
from django.db import transaction

def apply_payout(wallet_id, amount):
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        wallet.balance = wallet.balance + amount
        wallet.save()
'''
    unrelated = '''
def format_name(user):
    return user.first_name + " " + user.last_name
'''
    cfg = dict(DEFAULTS)
    fb = scan_source(bad, "bad.py", cfg)
    fg = scan_source(good, "good.py", cfg)
    fu = scan_source(unrelated, "unrelated.py", cfg)

    ok = True

    if not fb:
        print("FAIL: bad handler produced no findings", file=sys.stderr); ok = False
    else:
        prob_txt = " ".join(p for f in fb for p in f["problems"])
        if "atomic" not in prob_txt or "select_for_update" not in prob_txt:
            print("FAIL: bad handler missing expected problems: %s" % prob_txt,
                  file=sys.stderr); ok = False
        else:
            print("PASS: bad handler flagged (%d finding(s): %s)"
                  % (len(fb), prob_txt))

    if fg:
        print("FAIL: good (atomic+lock) handler flagged: %s"
              % [(f["func"], f["problems"]) for f in fg], file=sys.stderr); ok = False
    else:
        print("PASS: good handler (atomic + select_for_update) is clean")

    if fu:
        print("FAIL: unrelated code flagged: %s" % fu, file=sys.stderr); ok = False
    else:
        print("PASS: unrelated non-money code is clean")

    # exercise the path-scanning + exit-code plumbing end to end
    with tempfile.TemporaryDirectory() as d:
        bp = os.path.join(d, "bad.py")
        open(bp, "w", encoding="utf-8").write(bad)
        total, _ = scan_paths([bp])
        if total < 1:
            print("FAIL: scan_paths did not surface the bad file", file=sys.stderr); ok = False
        else:
            print("PASS: scan_paths surfaced the bad file (%d finding(s))" % total)

    print("\nSELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
