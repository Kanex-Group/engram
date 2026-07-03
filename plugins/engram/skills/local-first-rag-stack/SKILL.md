---
name: local-first-rag-stack
description: >-
  Reference architecture for a privacy-first, no-cloud RAG app — SQLite (embeddings in JSON) + local Ollama
  (embed+chat) + Tauri shell, with the cloud tier deferred behind one interface. Includes local-LLM ops
  tuning. Use when building a local-first AI app or choosing a RAG stack. Pairs with obrain-schema.
---

# local-first-rag-stack  ·  applies-when: building a local-first / privacy-first AI (RAG) app

## The shape
- **Storage:** SQLite, embeddings in a JSON column (no vector DB needed at small scale).
- **AI:** **local Ollama** for both embeddings (`all-minilm`-class) and chat; raw content never leaves the device.
- **Shell:** Tauri (native window) — Rust only as the shell.
- **Cloud tier is deferred behind ONE interface:** Postgres/pgvector, Redis/Celery, cloud LLM, object storage
  are an *optional* later layer behind the same `cheap_completion()`/`premium_completion()` seam — feature
  code never names a model or a backend. Local-first works today; cloud is a config flip later.

## Local-LLM ops tuning (the gotchas)
- **Cap embedding input** to the model's token window; **retry transient warm-up 5xx** (cold model load).
- Give the non-stream generate path a **generous timeout** (cold CPU reload) or use **streaming**.
- On a **non-citation backend, keep citations honestly empty** — never fabricate them to fill the field.

> Privacy is the win: raw user content (documents, notes, etc.) stays on the device by default.

Up: [capabilities.md](../../capabilities.md)
