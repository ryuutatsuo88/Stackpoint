# Stackpoint Take-Home — Loan Document Extraction

End-to-end system that ingests a loan-document corpus, extracts structured borrower data with an LLM, and serves it through a polished web UI. Built around three principles:

1. **Extraction logic and data shape are the contract.** A single Pydantic schema is the source of truth; TypeScript types are generated from it. Adding a new doc type means defining a schema, not rewriting glue.
2. **The LLM is replaceable.** Provider lives behind a thin `LLMProvider` interface; Claude is the default, OpenAI is a stub showing the swap is real, and a fake provider drives deterministic tests.
3. **Schemas evolve safely.** A novel-field detector flags any structured field the LLM finds in a document that isn't in the canonical schema, so new doc types can't silently regress the model.

> **Why JSON-on-disk instead of a database?** This is a take-home. The web app reads through a `BorrowerRepository` interface so swapping JSON for Postgres is one file. See [docs/design.md](docs/design.md).

## Layout

```
apps/
  extractor/   # Python — ingestion, classification, extraction, aggregation
  web/         # Next.js — UI + read API over extractor output
documents/     # The corpus (Loan 214/)
docs/          # Requirements, design, schema, task tracker
```

## Setup

Requirements: **Python ≥ 3.11**, **Node ≥ 20**, **uv**, **pnpm** (or npm).

```bash
# 1. Get an Anthropic API key (https://console.anthropic.com) and set it
cp .env.example .env
# edit .env and paste your ANTHROPIC_API_KEY

# 2. Install
cd apps/extractor && uv sync
cd ../web && pnpm install

# 3. Run the extractor over the corpus
cd ../extractor && uv run extractor run --corpus ../../documents

# 4. Start the web app
cd ../web && pnpm dev
# → http://localhost:3000
```

## Tests

```bash
cd apps/extractor && uv run pytest          # Python unit + integration
cd ../web && pnpm test                       # Vitest
cd ../web && pnpm exec playwright test       # E2E
```

## Architectural decisions (one-liners)

- **Pydantic-first schema.** The data model in `apps/extractor/src/extractor/schema.py` is the contract; JSON Schema is exported from it and consumed by the web app via `apps/web/lib/types.ts`.
- **PDF-native LLM input.** Claude accepts PDFs directly — no OCR, no fragile text extraction; we send the file and ask for a structured response.
- **Provider abstraction.** `LLMProvider` Protocol with `claude.py`, `openai.py` (stub), and `fake.py` (tests). Swapping providers is one env var.
- **Novel-field detection.** After the per-doc-type extraction, an open-ended pass diffs detected fields against the schema; novel fields get logged to `flags.json` for human review and surface in the `/flags` page in the UI.
- **Provenance everywhere.** Every extracted field carries `{source_path, page, confidence}`. The UI renders the original PDF beside the structured value.
- **JSON-on-disk + repository pattern.** `BorrowerRepository` is the seam. Today it reads JSON; tomorrow it reads Postgres. The UI doesn't change.

See [docs/design.md](docs/design.md) for the full system design and component diagram.
