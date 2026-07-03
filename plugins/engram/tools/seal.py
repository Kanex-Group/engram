#!/usr/bin/env python3
"""
Engram — Seal Tool
==================
Locks a private directory with a password ONLY YOU know, and gives your
governance structure tamper-evidence.

The password is read interactively with getpass — it is NEVER passed on the
command line, NEVER printed (except once by `genseal`), NEVER written to disk.
No agent, hook, or log can capture it. You generate it however you like (your
own script, a manager, whatever) and paste it in. Rotate it any time.

Everything project-specific — which directory is protected, the lock file
names, the governance file/dir list, and the optional append-only inbox — comes
from a config file. NOTHING is hardcoded. Copy engram.config.example.json to
engram.config.json (or point ENGRAM_CONFIG at it) and edit it for your repo.

Commands:
  python seal.py genseal   generate a random 6-char alphanumeric password, show it ONCE, then lock
  python seal.py lock      encrypt <protected_dir>/  ->  <locked_file>   (you type your own password)
  python seal.py unlock    decrypt <locked_file>  ->  <protected_dir>/
  python seal.py rotate    change the password (unlock with old, re-lock with new)
  python seal.py snapshot  record SHA-256 of every governance note -> <structure_lock>,
                           and of each append-only inbox entry -> <append_only.lock>
  python seal.py verify    detect any unauthorized modify/remove of the structure,
                           and any edit/deletion of a past inbox entry (append-only)

Config resolution (first that exists wins):
  1. $ENGRAM_CONFIG
  2. ./engram.config.json  (cwd)
  3. engram.config.json next to this script
  4. built-in defaults (protected_dir="private", locked_file="private.locked", ...)

Requires: pip install cryptography   (stdlib only otherwise)
WARNING: if you lose the password, the locked file CANNOT be recovered. That is the point.
"""
import os, sys, io, re, tarfile, hashlib, getpass, json, base64, secrets, shutil, string

HERE = os.path.dirname(os.path.abspath(__file__))
MAGIC = b"ENGRSEL1"

DEFAULTS = {
    "root": ".",
    "seal": {"protected_dir": "private", "locked_file": "private.locked"},
    "tamper": {
        "structure_lock": "structure.lock",
        "governance_dirs": [],
        "governance_files": [],
        "governance_globs": ["*.md"],
    },
    "append_only": {
        "file": "",
        "lock": "append-only.lock",
        "entry_heading_regex": r"^###\s+([A-Z]+-\d+)\b",
        "footer_strip_regex": r"\n+Up:[^\n]*\s*\Z",
    },
}


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_config():
    candidates = []
    env = os.environ.get("ENGRAM_CONFIG")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(os.getcwd(), "engram.config.json"))
    candidates.append(os.path.join(HERE, "engram.config.json"))
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    user = json.load(f)
            except (OSError, ValueError) as e:
                sys.exit("Config error in %s: %s" % (path, e))
            # drop any "_comment" keys at any level (JSON has no comments)
            user = _strip_comments(user)
            return _deep_merge(DEFAULTS, user), path
    return dict(DEFAULTS), None


def _strip_comments(obj):
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if k != "_comment"}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


class Ctx:
    """Resolved absolute paths for the current config."""
    def __init__(self, cfg, cfg_path):
        self.cfg = cfg
        self.cfg_path = cfg_path
        # root is relative to the config file's dir if we loaded one, else cwd
        base = os.path.dirname(cfg_path) if cfg_path else os.getcwd()
        self.root = os.path.abspath(os.path.join(base, cfg.get("root", ".")))
        s = cfg["seal"]
        self.protected = os.path.join(self.root, s["protected_dir"])
        self.protected_arcname = s["protected_dir"]
        self.locked = os.path.join(self.root, s["locked_file"])
        t = cfg["tamper"]
        self.struct = os.path.join(self.root, t["structure_lock"])
        self.gov_dirs = t.get("governance_dirs", [])
        self.gov_files = t.get("governance_files", [])
        self.gov_globs = t.get("governance_globs", ["*.md"]) or ["*.md"]
        a = cfg.get("append_only", {})
        self.ap_file = os.path.join(self.root, a["file"]) if a.get("file") else ""
        self.ap_lock = os.path.join(self.root, a.get("lock", "append-only.lock"))
        self.ap_heading = a.get("entry_heading_regex", DEFAULTS["append_only"]["entry_heading_regex"])
        self.ap_footer = a.get("footer_strip_regex", DEFAULTS["append_only"]["footer_strip_regex"])


def _fernet(password, salt):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.fernet import Fernet
    key = Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def _ask(confirm=False):
    pw = getpass.getpass("Password: ")
    if not pw:
        sys.exit("Empty password refused.")
    if confirm and pw != getpass.getpass("Confirm : "):
        sys.exit("Passwords did not match — nothing changed.")
    return pw


def _seal_bytes(ctx, pw):
    salt = secrets.token_bytes(16)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        tar.add(ctx.protected, arcname=ctx.protected_arcname)
    token = _fernet(pw, salt).encrypt(buf.getvalue())
    with open(ctx.locked, "wb") as f:
        f.write(MAGIC); f.write(salt); f.write(token)
    shutil.rmtree(ctx.protected)


def lock(ctx):
    if os.path.exists(ctx.locked):
        sys.exit("Already locked (%s exists). Use unlock or rotate." % os.path.basename(ctx.locked))
    if not os.path.isdir(ctx.protected):
        sys.exit("No %s/ to lock." % ctx.cfg["seal"]["protected_dir"])
    pw = _ask(confirm=True)
    _seal_bytes(ctx, pw)
    print("Locked. %s/ is encrypted into %s and the plaintext is removed."
          % (ctx.cfg["seal"]["protected_dir"], os.path.basename(ctx.locked)))
    print("Guard your password — without it this cannot be recovered.")


def unlock(ctx):
    if not os.path.exists(ctx.locked):
        sys.exit("Nothing locked.")
    pw = _ask()
    with open(ctx.locked, "rb") as f:
        magic, salt, token = f.read(8), f.read(16), f.read()
    if magic != MAGIC:
        sys.exit("Not a valid sealed vault.")
    from cryptography.fernet import InvalidToken
    try:
        data = _fernet(pw, salt).decrypt(token)
    except InvalidToken:
        sys.exit("Wrong password — nothing changed.")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        try:
            tar.extractall(ctx.root, filter="data")   # py3.12+
        except TypeError:
            tar.extractall(ctx.root)
    os.remove(ctx.locked)
    print("Unlocked. %s/ restored." % ctx.cfg["seal"]["protected_dir"])


def rotate(ctx):
    print("Enter your CURRENT password to unlock:")
    unlock(ctx)
    print("Now set a NEW password:")
    lock(ctx)


def _fnmatch_any(name, patterns):
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _manifest(ctx):
    man = {}
    for d in ctx.gov_dirs:
        base = os.path.join(ctx.root, d)
        for root, _, files in os.walk(base):
            for fn in files:
                if _fnmatch_any(fn, ctx.gov_globs):
                    fp = os.path.join(root, fn)
                    with open(fp, "rb") as f:
                        man[os.path.relpath(fp, ctx.root).replace("\\", "/")] = hashlib.sha256(f.read()).hexdigest()
    for fn in ctx.gov_files:
        fp = os.path.join(ctx.root, fn)
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                man[fn.replace("\\", "/")] = hashlib.sha256(f.read()).hexdigest()
    return man


def _append_only_manifest(ctx):
    """Per-entry SHA-256 of the append-only inbox, keyed by entry id."""
    man = {}
    if not ctx.ap_file or not os.path.exists(ctx.ap_file):
        return man
    with open(ctx.ap_file, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    if ctx.ap_footer:
        text = re.sub(ctx.ap_footer, "\n", text)   # strip the note footer so a new append doesn't false-flag the prior last entry
    # split on the heading; capture group 1 is the entry id
    heading = re.compile(ctx.ap_heading, re.M)
    matches = list(heading.finditer(text))
    for i, m in enumerate(matches):
        pid = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        man[pid] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return man


def snapshot(ctx):
    man = _manifest(ctx)
    with open(ctx.struct, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, sort_keys=True)
    print("Snapshot written: %d governance notes hashed -> %s" % (len(man), os.path.basename(ctx.struct)))
    if ctx.ap_file:
        pman = _append_only_manifest(ctx)
        with open(ctx.ap_lock, "w", encoding="utf-8") as f:
            json.dump(pman, f, indent=2, sort_keys=True)
        print("Append-only snapshot: %d inbox entries hashed -> %s" % (len(pman), os.path.basename(ctx.ap_lock)))


def verify(ctx):
    if not os.path.exists(ctx.struct):
        sys.exit("No %s - run `snapshot` first." % os.path.basename(ctx.struct))
    old = json.load(open(ctx.struct, encoding="utf-8"))
    cur = _manifest(ctx)
    modified = [k for k in old if k in cur and cur[k] != old[k]]
    removed  = [k for k in old if k not in cur]
    added    = [k for k in cur if k not in old]

    # Append-only inbox: editing/removing a past entry is tampering; new entries are allowed.
    p_mod = p_rem = p_add = []
    if ctx.ap_file and os.path.exists(ctx.ap_lock):
        pold = json.load(open(ctx.ap_lock, encoding="utf-8"))
        pcur = _append_only_manifest(ctx)
        p_mod = [k for k in pold if k in pcur and pcur[k] != pold[k]]
        p_rem = [k for k in pold if k not in pcur]
        p_add = [k for k in pcur if k not in pold]

    if not (modified or removed or p_mod or p_rem):
        print("OK - no unauthorized structural changes.")
        for k in added:
            print("  + (additive, allowed):", k)
        for k in p_add:
            print("  + (entry added, allowed):", k)
        return
    print("GATED CHANGE DETECTED - needs the sealed key / owner review:")
    for k in modified:
        print("  modified:", k)
    for k in removed:
        print("  removed :", k)
    for k in p_mod:
        print("  entry MODIFIED (append-only violation!):", k)
    for k in p_rem:
        print("  entry REMOVED (append-only violation!):", k)
    for k in added:
        print("  + (additive, allowed):", k)
    for k in p_add:
        print("  + (entry added, allowed):", k)
    sys.exit(1)


def _genpw(n=6):
    alphabet = string.ascii_letters + string.digits   # 62 chars, crypto-strong via secrets
    return "".join(secrets.choice(alphabet) for _ in range(n))


def genseal(ctx):
    """Generate a random 6-char alphanumeric password, show it ONCE, then lock the protected dir."""
    if os.path.exists(ctx.locked):
        sys.exit("Already locked. Use unlock or rotate.")
    if not os.path.isdir(ctx.protected):
        sys.exit("No %s/ to lock." % ctx.cfg["seal"]["protected_dir"])
    pw = _genpw(6)
    _seal_bytes(ctx, pw)
    print("=" * 54)
    print("  GENERATED PASSWORD  (shown ONCE — save it NOW):")
    print()
    print("        " + pw)
    print()
    print("  It is NOT stored anywhere. Lose it and the sealed dir")
    print("  cannot be recovered. Rotate any session with `rotate`.")
    print("=" * 54)


CMDS = {"genseal": genseal, "lock": lock, "unlock": unlock, "rotate": rotate,
        "snapshot": snapshot, "verify": verify}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__)
    cfg, cfg_path = _load_config()
    ctx = Ctx(cfg, cfg_path)
    try:
        CMDS[sys.argv[1]](ctx)
    except ImportError:
        sys.exit("Missing dependency. Run:  pip install cryptography")
