# Engram — Capabilities Manifest

The source of truth for `brain-sync`. Each capability declares an **`applies-when`** tag so the sync
check only proposes what's relevant. `status`: `in-core` (ready to adopt) · `to-extract` (still lives
in a project, needs generalizing into Core) · `planned`.

## Layer A — Capabilities (skills)

| id | applies-when | status | version | notes |
|---|---|---|---|---|
| `brain-sync` | every project using engram | **in-core** | 0.1.0 | the sync ritual itself |
| `vault-lookup` | project has an OBrain/Obsidian vault | **in-core** | 0.3.0 | index-first read policy + session loop; safe branch-hop on repo-doc edits |
| `new-dev-note` | project uses the Dev_Sessions spine | **in-core** | 0.2.0 | scaffolds Session/Issue/Fix/Feature/Handoff |
| `wiki-sync` | project mirrors code into a derived Wiki | **in-core** | 0.2.0 | Karpathy LLM-Wiki Ingest op |
| `vault-lint` | project has an OBrain vault | **in-core** | 0.2.0 | broken-link/orphan/stale-path/drift scan |
| `pre-merge-check` | project ships code to prod | **in-core** | 0.2.0 | typed QA & merge gate; per-project approval phrase |
| `money-path-guard` | **project handles real money** | **in-core** | 0.2.0 | lock + idempotency + ledger invariant |
| `company-layer` | project needs a business/ops layer beside its dev spine | **in-core** | 0.1.0 | scoped propose-only function-nodes + AI-CEO + Human-Gate |
| `brain-first-hook` | node keeps drifting from its vault after /clear | **in-core** | 0.1.0 | SessionStart hook enforces brain-first |
| `harden-upload` | project has a file-upload/ingest endpoint | **in-core** | 0.1.0 | allowlist→early size cap→sniff→wrap-to-400→auth-separate |
| `local-first-rag-stack` | building a local-first/privacy AI app | **in-core** | 0.1.0 | SQLite+Ollama+Tauri; cloud tier deferred; local-LLM ops |
| `deploy-release` | project ships code to prod | **in-core** | 0.1.0 | exact-phrase gate + release agent + data hygiene + required-vs-built |
| `debug-triage` | debugging or auditing "done" work | **in-core** | 0.1.0 | infra-vs-code by error-shape, claims-vs-reality, ID contract, verify-the-artefact |

## Layer B — Methods / habits

| id | applies-when | status | notes |
|---|---|---|---|
| `obrain-schema` | any project wanting a knowledge base | **in-core** | folder schema, indexes, graph colors |
| `learn-mode` | any project | **in-core** | the Learn/ folder + discuss→converge→implement |
| `qa-merge-gate` | project ships code to prod | **encoded** | lives inside `pre-merge-check` |
| `llm-wiki-ops` | project has a codebase to mirror | **encoded** | Ingest=`wiki-sync`, Lint=`vault-lint`, Query=`vault-lookup` |
| `session-spine` | any project | **encoded** | lives inside `vault-lookup` + `new-dev-note` |
| `visualize-mode` | any project | **planned — NOT built (no SKILL.md)** | render to a rich Obsidian note on "make it visual" |

## Layer C — Human layer
See `human/` — personal truth about the human(s) driving the brain. Adopted into every project's
context so each one "knows you the same way." Multiple personas supported. This layer is a **template**
in the public release — fill it in locally; it never leaves your machine.

## Layer D — Project secrets
**Not tracked here. Never enters Core.** (e.g. secret thresholds, credentials, live file:line issue
lists, domain-specific private content.) Layer D stays local to each project and must never be synced up.
