#!/usr/bin/env python3
"""Shared helpers for the Engram Tier 2 git hooks.

Pure Python 3 stdlib. Cross-platform (Windows git-bash, macOS, Linux).
Loads config from ``engram.hooks.json`` (searched in the hooks dir and repo
root); falls back to built-in defaults matching the build spec when absent.

No personal, business, node, or vault names live here. This ships PUBLIC.
"""

import json
import os
import subprocess
import sys

# --- Built-in defaults (must mirror the shipped engram.hooks.json) -----------

DEFAULT_CONFIG = {
    "protected_branches": ["main", "master"],
    "qa": {
        "dir": "QA",
        "record_glob": "QA_*.md",
        "passed_marker": "status: PASSED",
    },
    "secret_scan": {
        "deny_paths": [
            "*.env",
            ".env",
            "secrets.*",
            "_dev_core/*",
            "*.locked",
        ],
        "deny_patterns": [
            r"-----BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY-----",
            r"AKIA[0-9A-Z]{16}",
            r"xox[baprs]-[0-9A-Za-z-]+",
            r"ghp_[A-Za-z0-9]{36}",
            r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}",
        ],
    },
    "fingerprint": {
        "deny_trailers": [
            r"Co-Authored-By: Claude",
            r"Co-Authored-By: .*anthropic",
            r"Generated with .*Claude",
        ]
    },
}

CONFIG_FILENAME = "engram.hooks.json"

# The (discouraged) emergency bypass strings, surfaced in every block message.
BYPASS_COMMIT = "git commit --no-verify   (discouraged; disables ALL commit hooks)"
BYPASS_PUSH = "git push --no-verify       (discouraged; disables ALL push hooks)"


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def repo_root():
    """Return the git repo top-level, or None if not in a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:
        pass
    return None


def _deep_merge(base, override):
    """Recursively merge ``override`` onto a copy of ``base``."""
    result = dict(base)
    for key, value in (override or {}).items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load config from the first ``engram.hooks.json`` found.

    Search order: the hooks ``git/`` dir, its parent (``hooks/``), and the repo
    root. Missing/broken config => built-in defaults. Present config is merged
    *onto* defaults so partial files still work.
    """
    here = _here()
    candidates = [
        os.path.join(here, CONFIG_FILENAME),
        os.path.join(os.path.dirname(here), CONFIG_FILENAME),
    ]
    root = repo_root()
    if root:
        candidates.append(os.path.join(root, CONFIG_FILENAME))

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    user_cfg = json.load(fh)
                return _deep_merge(DEFAULT_CONFIG, user_cfg)
            except (ValueError, OSError) as exc:
                sys.stderr.write(
                    "[engram] warning: could not read %s (%s); "
                    "using built-in defaults\n" % (path, exc)
                )
                break
    return dict(DEFAULT_CONFIG)


def eprint(msg=""):
    """Print to stderr (hook diagnostics go to stderr, not stdout)."""
    sys.stderr.write(msg + "\n")
