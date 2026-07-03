# Engram

**Persistent memory _and guardrails_ for AI coding agents — your agent remembers your project across
sessions, and can't quietly break it.**

An *engram* is the physical trace a memory leaves in the brain. This is that, for your AI coding agent:
a portable, local knowledge base plus a set of skills that let an agent **orient from what's already
known** instead of re-deriving your project every session — backed by **enforcement hooks the agent
can't skip** (secret-scan, a QA merge-gate, no-push-to-`main`-without-review). Memory so it remembers;
guardrails so it can't silently do something dangerous.

Engram is packaged as a [Claude Code](https://claude.com/claude-code) plugin. Drop it into any project
and your agent gains a durable "brain": a structured Obsidian-style vault (**OBrain**), a session spine
that survives `/clear` and context resets, a code-mirroring wiki so it stops re-reading your source, and
a library of battle-tested engineering methods (QA gate, money-path guardrails, deploy discipline, upload
hardening, and more).

> **Status:** v1.2.1.
>
> 🚀 **New here? Start with the [Getting Started guide](docs/GETTING-STARTED.md)** — it takes you from
> zero to a working setup in a couple of minutes, no prior experience needed. The short version: install
> the plugin, then tell your agent *"set up Engram for this project"* and work normally.

---

## Why

LLM agents forget. Every new session, every context compaction, every `/clear` throws away hard-won
understanding of *your* project — its architecture, its decisions, why something is the way it is. You
end up re-explaining. Engram fixes that by writing knowledge **down**, in files, and teaching the agent to
read them **first**:

- **Continuity** — a Session → Issues → Fixes → Handoff loop the agent picks up automatically next time.
- **Orientation** — an index-first read policy so the agent consults the brain before acting, and keeps
  its context lean.
- **Less drift** — a `SessionStart` hook that makes "read the vault first" a harness guarantee, not
  something the model chooses to remember.
- **Portable method** — the same skills, QA gate, and conventions apply across every project you use it in.

## Privacy

- **Runs 100% locally.** Engram is plain Markdown files in your repo plus plugin skills. Your brain lives
  on your machine.
- **No telemetry.** It phones home to nobody. There is no analytics, no tracking, no account.
- **No auto-sync.** Nothing is uploaded anywhere. The only way anything leaves your machine is if **you**
  choose to open a pull request to this repo.
- The **human layer** (personal-truth profile) ships as a blank template — you fill it in locally.

## Install

Engram is a Claude Code plugin distributed as a marketplace in this repo.

```
# 1. Add this repository as a plugin marketplace
/plugin marketplace add Kanex-Group/engram

# 2. Install the Engram plugin
/plugin install engram@engram
```

Then start a session in any project and run **`brain-sync`** (or ask your agent to "sync the brain"). If
the project has no vault yet, ask it to scaffold one with the **`obrain-schema`** skill.

> Requires [Claude Code](https://claude.com/claude-code). Obsidian is recommended for viewing/editing the
> vault, but not required — it's all Markdown.

## What's inside

**Layer A — Capability skills**

| skill | use it when |
|---|---|
| `brain-sync` | start of a session — pull shared improvements, propose adoptions |
| `vault-lookup` | look things up in / operate the project's vault |
| `new-dev-note` | scaffold a Session / Issue / Fix / Feature / Handoff note |
| `wiki-sync` | mirror code into a derived wiki after changing it |
| `vault-lint` | health-check the vault for broken links / drift |
| `pre-merge-check` | run a typed QA & merge gate before shipping to prod |
| `money-path-guard` | before editing payments / wallets / ledgers / payouts |
| `company-layer` | stand up a business/ops layer beside the dev spine |
| `brain-first-hook` | a node keeps drifting from its vault after `/clear` |
| `harden-upload` | adding or reviewing a file-upload / ingest endpoint |
| `local-first-rag-stack` | building a local-first / privacy-first AI app |
| `deploy-release` | shipping / deploying to prod safely |
| `debug-triage` | debugging or auditing "is it really done?" work |

**Layer B — Methods:** `obrain-schema` (the vault schema), `learn-mode` (discuss → converge → implement),
plus encoded QA-merge-gate, LLM-Wiki ops, and the session spine.

**Layer C — Human layer:** an optional personal-truth profile so every project "knows you the same way."
Ships as a template; stays local.

## Contributing

Contributions are welcome and **opt-in** — nothing is shared unless you open a PR.

1. Fork → branch off `main` → make your change.
2. Open a pull request; the owner reviews and approves every merge.
3. By contributing you agree to the [CLA](CLA.md): your work is licensed to the public under AGPL-3.0 and
   you grant Kanex Group the right to relicense it (enabling future dual-licensing).

Please don't include personal data, secrets, or private project content. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the details.

## License

Engram is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE).
Copyright © 2026 **Kanex Group**.

AGPL means: you can use, study, modify, and share it freely, but if you run a modified version as a
network service you must offer your users its source. If those terms don't work for your use case, a
**commercial license is available** — contact the owner (Kanex Group). See [NOTICE](NOTICE).
