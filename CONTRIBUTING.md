# Contributing to Engram

Engram is open source under the **AGPL-3.0** and welcomes contributions. It runs **100% locally** and
collects **no telemetry** — so contributing is entirely **opt-in**: nothing leaves your machine unless
*you* choose to open a pull request.

## How contributions work

1. **Fork** this repository to your own account.
2. **Branch** off `main` for your change (`git checkout -b my-change`).
3. **Make your change.** Keep skills generic and portable — Engram's value is methodology that applies
   across projects, not project-specific detail. Never include personal data, credentials, or anything
   from a private project (see "What not to include" below).
4. **Open a pull request** against this repository's `main`.
5. **The owner reviews and approves.** Merge is at the maintainer's (Kanex Group's) discretion. There is
   no automatic merge; a human owner approves every change.

## Licensing of contributions — please read

By opening a pull request you agree to the **Engram Contributor License Agreement** ([CLA.md](CLA.md)).
In short:

- Your contribution is licensed to the public under the **AGPL-3.0**, the same as the rest of the project.
- You **also** grant Kanex Group the right to license your contribution under other terms. This is what
  lets Engram be offered under both an open-source license and a **commercial license** in the future
  (dual-licensing).
- You keep the copyright to your own work — the CLA is a grant of rights, not a transfer of ownership.

If you don't agree with the CLA, please don't submit a pull request.

## What not to include

Engram was extracted from a working private "brain," so we're strict about this. Please do **not** submit:

- Personal or contact information (names, emails, handles) other than standard commit authorship.
- Credentials, secrets, tokens, or `.env` contents.
- Private/company-internal project data, financials, or "Layer D" project secrets.
- Anything you're not authorized to publish.

## Style

- Match the existing terse, technical voice in the skill files.
- A skill (`SKILL.md`) needs YAML frontmatter with a `name` and a `description` that says **when** to use
  it. Keep the description trigger-focused.
- Prefer generic, checkable rules (numbers, not adjectives) over prose.

## Reporting issues

Open a GitHub issue. Please don't paste private data into issues.

## Questions / commercial licensing

For anything else — including a commercial license — contact the owner, **Kanex Group**.
