---
name: harden-upload
description: >-
  The hardening order for any "user uploads a file → we parse it" endpoint: extension allowlist → early size
  cap → content-sniff → wrap the parser to 400 → auth is separate. Use whenever adding/reviewing a file
  upload or ingest path. Pairs with pre-merge-check, money-path-guard.
---

# harden-upload  ·  applies-when: a project has a file-upload / ingest endpoint

A repeatable guard **order** (order matters — each step assumes the previous passed):

1. **Extension allowlist** — reject unknown types up front.
2. **Size cap, checked EARLY** — test `file.size` *before* buffering the whole file into memory (a late check
   already paid the memory cost).
3. **Content-sniff** — magic-byte check (`%PDF` header; reject NUL bytes in a "text" file) so a **renamed
   binary** can't slip past the extension check.
4. **Wrap the parser** — any third-party parser exception (corrupt / truncated / encrypted) → map to a clean
   **400, never an uncaught 500.**
5. **Auth is a separate decision** — flag it explicitly; don't guess an auth model into the upload path.

> Same family as `money-path-guard`: untrusted input gets validated *before* it can do damage. Verify with a
> renamed-binary + a corrupt-file test, not just a happy-path upload.

Up: [capabilities.md](../../capabilities.md)
