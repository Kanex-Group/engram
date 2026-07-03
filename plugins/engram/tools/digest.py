#!/usr/bin/env python3
"""Audit digest — "what changed since I last reviewed?".

When commits can land automatically (auto-commit / auto-adopt), silent must not
mean invisible. This lists commits made since the last review marker
(.engram_review at the repo root) and flags automated commits by a configurable
trailer (default: a line beginning `Brain:`).

  python digest.py            show commits since last review (else last 20)
  python digest.py --mark     record HEAD as reviewed (resets the digest)
  python digest.py --trailer Auto   flag commits whose body has an `Auto:` line

Pure stdlib. Finds the git repo root itself, so it works from anywhere in the tree.
"""
import os, sys, subprocess


def _git(root, *a):
    r = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)
    return r.stdout.strip()


def _repo_root(start):
    r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Not inside a git repository.")
    return r.stdout.strip()


def main(argv):
    root = _repo_root(os.getcwd())
    mark = os.path.join(root, ".engram_review")

    trailer = "Brain"
    if "--trailer" in argv:
        i = argv.index("--trailer")
        if i + 1 < len(argv):
            trailer = argv[i + 1]

    if "--mark" in argv:
        head = _git(root, "rev-parse", "HEAD")
        with open(mark, "w", encoding="utf-8") as f:
            f.write(head + "\n")
        print("Marked reviewed at", head[:8])
        return

    since = ""
    if os.path.exists(mark):
        since = open(mark, encoding="utf-8").read().strip()
    rng = since + "..HEAD" if since else "-20"
    out = _git(root, "log", "--pretty=format:%h\x1f%ci\x1f%s\x1f%b\x1e", rng)
    records = [r for r in out.split("\x1e") if r.strip()]

    label = ("since " + since[:8]) if since else "(last 20)"
    print("=== Audit digest: %d commit(s) %s ===" % (len(records), label))
    tprefix = (trailer + ":").lower()
    for r in records:
        parts = r.strip().split("\x1f")
        h, ci, subj = parts[0], parts[1], parts[2]
        body = parts[3] if len(parts) > 3 else ""
        tag = ""
        for line in body.splitlines():
            if line.strip().lower().startswith(tprefix):
                tag = "  [" + line.split(":", 1)[1].strip() + "]"
        print("  %s %s  %s%s" % (h, ci[:10], subj, tag))
    print("\nRun `python digest.py --mark` once you've reviewed.")


if __name__ == "__main__":
    main(sys.argv[1:])
