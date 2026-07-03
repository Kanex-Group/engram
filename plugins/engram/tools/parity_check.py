#!/usr/bin/env python3
"""Parity check — capabilities.md <-> skills/ must agree.

Enforces two-way parity inside a plugin dir:
  * every `in-core` capability row in capabilities.md has a matching
    skills/<id>/SKILL.md on disk               (missing skill = broken manifest)
  * every skills/<id>/SKILL.md is declared as an `in-core` row
    in capabilities.md                          (ghost skill = undeclared capability)

Rows whose status is NOT `in-core` (e.g. `to-extract`, `planned`, `encoded`) are
NOT required to have a skill, and are ignored by the "ghost" direction too — but a
skill dir that exists while its row says `planned`/`to-extract` is still a ghost
(it ships code the manifest says isn't ready), so those are reported.

  python parity_check.py <plugin_dir>
  python parity_check.py --selftest

<plugin_dir> is the folder holding capabilities.md and skills/ (e.g.
.../plugins/engram). Exits non-zero on any mismatch; prints each one.

Config (optional): engram.hooks.json under "parity" key, discovered at
<plugin_dir>/hooks/engram.hooks.json or <plugin_dir>/engram.hooks.json:
  parity.capabilities_file  (default "capabilities.md")
  parity.skills_dir         (default "skills")
  parity.skill_manifest     (default "SKILL.md")
  parity.required_status    (default "in-core")  status that mandates a skill
  parity.ignore_ids         ([str]) capability ids never required to have a skill
"""
import os
import sys
import re
import json

DEFAULTS = {
    "capabilities_file": "capabilities.md",
    "skills_dir": "skills",
    "skill_manifest": "SKILL.md",
    "required_status": "in-core",
    "ignore_ids": [],
}

# a table row:  | `id` | ... | status-cell | ... |
ROW_RE = re.compile(r"^\|(.+)\|\s*$")
# grab first backticked token in the id cell
ID_RE = re.compile(r"`([^`]+)`")


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _load_config(plugin_dir):
    cfg = dict(DEFAULTS)
    for c in (os.path.join(plugin_dir, "hooks", "engram.hooks.json"),
              os.path.join(plugin_dir, "engram.hooks.json")):
        if os.path.isfile(c):
            try:
                data = json.loads(_read(c))
            except Exception:
                continue
            sub = data.get("parity", {})
            if isinstance(sub, dict):
                cfg.update({k: v for k, v in sub.items() if k in DEFAULTS})
            break
    return cfg


def _parse_capabilities(text, required_status):
    """Return (required_ids, declared_ids).

    required_ids  = ids whose status cell contains required_status
    declared_ids  = every id that appears in any capability table row
    A row is a capability row if its first cell is a single `backticked` id and
    the header separator/`id`-header lines are skipped.
    """
    required = set()
    declared = set()
    req_low = required_status.lower()
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells:
            continue
        first = cells[0]
        # skip header rows ("id", "---") and separators
        idm = ID_RE.search(first)
        if not idm:
            continue
        cap_id = idm.group(1).strip()
        # heuristic: the id cell is ONLY the backticked token (+ maybe bold **)
        stripped = first.replace("*", "").strip()
        if not (stripped.startswith("`") and stripped.rstrip().endswith("`")):
            continue
        declared.add(cap_id)
        rowtext = " ".join(cells).lower()
        if req_low in rowtext:
            required.add(cap_id)
    return required, declared


def _list_skills(plugin_dir, cfg):
    sdir = os.path.join(plugin_dir, cfg["skills_dir"])
    found = {}
    if not os.path.isdir(sdir):
        return found
    for name in sorted(os.listdir(sdir)):
        d = os.path.join(sdir, name)
        if os.path.isdir(d):
            found[name] = os.path.isfile(os.path.join(d, cfg["skill_manifest"]))
    return found


def check(plugin_dir, cfg):
    """Return list of (kind, id, detail)."""
    caps_path = os.path.join(plugin_dir, cfg["capabilities_file"])
    problems = []
    if not os.path.isfile(caps_path):
        return [("no-manifest", cfg["capabilities_file"],
                 "not found in %s" % plugin_dir)]
    required, declared = _parse_capabilities(_read(caps_path),
                                             cfg["required_status"])
    skills = _list_skills(plugin_dir, cfg)
    ignore = set(cfg["ignore_ids"])

    # missing: required in manifest but no skill dir / no SKILL.md
    for cap in sorted(required):
        if cap in ignore:
            continue
        if cap not in skills:
            problems.append(("missing-skill", cap,
                             "%s row is '%s' but skills/%s/ absent"
                             % (cap, cfg["required_status"], cap)))
        elif not skills[cap]:
            problems.append(("missing-manifest", cap,
                             "skills/%s/ exists but no %s"
                             % (cap, cfg["skill_manifest"])))

    # ghost: skill dir on disk not declared in-core in the manifest
    for name, has_manifest in skills.items():
        if name in ignore:
            continue
        if not has_manifest:
            continue  # dir without a manifest isn't a shipped skill
        if name not in required:
            if name in declared:
                problems.append(("ghost-skill", name,
                                 "skills/%s/ ships but its row is not '%s'"
                                 % (name, cfg["required_status"])))
            else:
                problems.append(("ghost-skill", name,
                                 "skills/%s/ ships but has no row in %s"
                                 % (name, cfg["capabilities_file"])))
    return problems


def run(plugin_dir):
    if not os.path.isdir(plugin_dir):
        sys.stderr.write("parity_check: not a directory: %s\n" % plugin_dir)
        return 2
    cfg = _load_config(plugin_dir)
    problems = check(plugin_dir, cfg)
    if not problems:
        print("parity_check: OK — capabilities.md and skills/ agree in %s"
              % plugin_dir)
        return 0
    problems.sort(key=lambda t: (t[0], t[1]))
    print("parity_check: %d mismatch(es) in %s" % (len(problems), plugin_dir))
    for kind, cid, detail in problems:
        print("  [%-16s] %s" % (kind, detail))
    sys.stderr.write(
        "\nparity_check FAILED: either add the SKILL.md, or fix the row's "
        "status in capabilities.md (a shipped skill must be 'in-core'; a "
        "planned one must not have a skills/ dir).\n")
    return 1


# --------------------------------------------------------------------------
def _selftest():
    import tempfile
    import shutil

    CAPS = (
        "# Caps\n\n"
        "## Layer A\n"
        "| id | applies-when | status | version | notes |\n"
        "|---|---|---|---|---|\n"
        "| `alpha` | x | **in-core** | 0.1.0 | ok |\n"
        "| `beta`  | y | **in-core** | 0.1.0 | ok |\n"
        "| `gamma` | z | planned — NOT built | | later |\n"
        "\n## Layer B\n"
        "| id | applies-when | status | notes |\n"
        "|---|---|---|---|\n"
        "| `delta` | any | **in-core** | method |\n"
    )

    def build(caps, skill_names):
        d = tempfile.mkdtemp(prefix="parity_")
        with open(os.path.join(d, "capabilities.md"), "w",
                  encoding="utf-8") as f:
            f.write(caps)
        for s in skill_names:
            sd = os.path.join(d, "skills", s)
            os.makedirs(sd, exist_ok=True)
            with open(os.path.join(sd, "SKILL.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\nname: %s\n---\nbody\n" % s)
        return d

    fails = []

    # PASS: all in-core rows have skills, no extra skills.
    # gamma is 'planned' -> not required, and no gamma skill dir -> fine.
    p = build(CAPS, ["alpha", "beta", "delta"])
    if run(p) != 0:
        fails.append("PASS fixture returned nonzero")
    shutil.rmtree(p, ignore_errors=True)

    # FAIL: missing skill (beta declared in-core, no dir)
    p = build(CAPS, ["alpha", "delta"])
    probs = check(p, dict(DEFAULTS))
    if not any(k == "missing-skill" and cid == "beta" for k, cid, d in probs):
        fails.append("missing-skill(beta) not detected: %r" % probs)
    if run(p) == 0:
        fails.append("missing-skill fixture returned 0")
    shutil.rmtree(p, ignore_errors=True)

    # FAIL: ghost skill (epsilon ships but no row)
    p = build(CAPS, ["alpha", "beta", "delta", "epsilon"])
    probs = check(p, dict(DEFAULTS))
    if not any(k == "ghost-skill" and cid == "epsilon" for k, cid, d in probs):
        fails.append("ghost-skill(epsilon) not detected: %r" % probs)
    shutil.rmtree(p, ignore_errors=True)

    # FAIL: ghost via wrong status (gamma is 'planned' but ships a dir)
    p = build(CAPS, ["alpha", "beta", "delta", "gamma"])
    probs = check(p, dict(DEFAULTS))
    if not any(k == "ghost-skill" and cid == "gamma" for k, cid, d in probs):
        fails.append("ghost-skill(gamma planned) not detected: %r" % probs)
    shutil.rmtree(p, ignore_errors=True)

    # FAIL: dir present but no SKILL.md
    p = build(CAPS, ["alpha", "beta", "delta"])
    os.makedirs(os.path.join(p, "skills", "beta"), exist_ok=True)
    os.remove(os.path.join(p, "skills", "beta", "SKILL.md"))
    probs = check(p, dict(DEFAULTS))
    if not any(k == "missing-manifest" and cid == "beta"
               for k, cid, d in probs):
        fails.append("missing-manifest(beta) not detected: %r" % probs)
    shutil.rmtree(p, ignore_errors=True)

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("parity_check --selftest: PASS "
          "(pass + missing-skill + ghost-skill + planned-ghost + "
          "missing-manifest)")
    return 0


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.stderr.write("usage: python parity_check.py <plugin_dir> | "
                         "--selftest\n")
        return 2
    return run(args[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
