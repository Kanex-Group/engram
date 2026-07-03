#!/bin/sh
# Shared launcher for the Engram git hooks.
# Resolves this script's own directory and a working Python 3 interpreter,
# then execs the requested hook script, passing through args + stdin.
#
# POSIX sh only. Works in Windows git-bash, macOS, Linux.

# Directory containing this file (and the hook scripts). $0 is the sh wrapper.
HOOK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Find a Python 3 interpreter.
PY=""
for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then
        # 'py' is the Windows launcher; force v3.
        if [ "$cand" = "py" ]; then
            if py -3 -c "import sys" >/dev/null 2>&1; then
                PY="py -3"
                break
            fi
            continue
        fi
        # Confirm it is Python 3.
        if "$cand" -c "import sys; sys.exit(0 if sys.version_info[0]==3 else 1)" >/dev/null 2>&1; then
            PY="$cand"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "[engram] hook error: no Python 3 interpreter found on PATH." >&2
    echo "         install Python 3 or bypass in emergency with --no-verify." >&2
    exit 1
fi

SCRIPT="$1"
shift

# exec so the hook's exit code is the wrapper's exit code; stdin flows through.
# shellcheck disable=SC2086
exec $PY "$HOOK_DIR/$SCRIPT" "$@"
