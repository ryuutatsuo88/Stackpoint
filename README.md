# Stackpoint Take-Home — Loan Document Extraction

End-to-end system that ingests a loan-document corpus, extracts structured borrower data with an LLM, surfaces cross-document conflicts and schema-novel fields, and serves the result through a polished web UI.

> Built around three principles: (1) a single Pydantic schema is the source of truth and every value carries provenance; (2) the LLM lives behind a thin Protocol, swappable in one env var; (3) the system tells you what it doesn't know — novel fields and cross-doc disagreements both surface for human review instead of being silently reconciled.

The full system design (architecture, component diagram, data flow, trade-offs) lives in [`docs/design.md`](docs/design.md). The data model is in [`docs/schema.md`](docs/schema.md).

---

## Layout

```
apps/
  extractor/   Python pipeline — discover → classify → extract → aggregate → JSON
  web/         Next.js 15 UI — borrower list, detail, flags review
documents/     The corpus (Loan 214/)
docs/          requirements · schema · design · task tracker
.env.example   Required env vars; Anthropic key MUST be supplied locally
```

## Setup

Requirements: **Python ≥ 3.12**, **Node ≥ 20**, **uv**, **pnpm** (or npm).

```bash
# 1. Get an Anthropic API key (https://console.anthropic.com)
cp .env.example .env
# edit .env and paste your ANTHROPIC_API_KEY

# 2. Install
cd apps/extractor && uv sync
cd ../web && pnpm install

# 3. Run the extractor over the corpus (real LLM call — costs ~$1-3 per run on Opus 4.7)
cd ../extractor
uv run extractor run --corpus ../../documents

# 4. Start the web app
cd ../web && pnpm dev
# → http://localhost:3000
```

## Environment

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | The repository will not commit `.env` (gitignored). Rotate the key after demo. |
| `LLM_PROVIDER` | no | `claude` | `claude` or `openai` (stub). |
| `LLM_MODEL` | no | `claude-opus-4-7` | Try `claude-sonnet-4-6` for ~3× cost reduction during dev. |
| `EXTRACTOR_OUTPUT_DIR` | no | `apps/web/data/output` | Where the pipeline writes JSON; the web app reads from here. |

## Tests

```bash
# Python — 35 unit + integration tests, no network needed
cd apps/extractor && uv run pytest

# Web — typecheck + build
cd apps/web && pnpm typecheck && pnpm build
```

The Python integration test exercises the full pipeline end-to-end against a `FakeProvider` seeded with realistic synthetic responses. If those pass, the same code path runs against the real `ClaudeProvider` — only the LLM I/O differs.

## What this system does, in concrete terms

Given the [Loan 214 corpus](documents/Loan%20Documents/Loan%20214/) — 10 PDFs covering paystub, W-2, EVOE, 1040 + Schedule C, checking and savings statements, Closing Disclosure, Title Report, Letter of Explanation, and a Form 1008 — it produces:

- A structured `Borrower` record with PII, full income history, employment, accounts, loan, and properties.
- **Provenance for every value.** Every scalar carries `{document_id, page, confidence}`. The UI renders a provenance pill next to each value linking back to its source.
- **Multi-source preservation.** When the same fact appears in N docs (legal name, address, SSN, loan ID, loan amount), all observations are kept. Primary picked by documented preference rules; alternates retained.
- **Cross-document consistency flags.** When sources disagree — three different "subject property" addresses across CD/1008/Title, Mary's SSN drifting between 1040 and 1008, loan IDs off by one digit, the Title Report being for an entirely different transaction — each becomes an `ExtractionFlag` shown in the UI. Nothing is silently reconciled.
- **Novel-field detection.** When the LLM spots a structured field that isn't in the schema (e.g. `advice_number` on a paystub), it returns a `NovelFieldHint` alongside the typed extraction. Promoting a hint to a real schema field is a code change; the UI tells you it's needed.

## Architectural decisions (one-liners)

- **Pydantic-first schema.** [`apps/extractor/src/extractor/schema.py`](apps/extractor/src/extractor/schema.py) is the contract. TypeScript mirrors live in [`apps/web/lib/types.ts`](apps/web/lib/types.ts) — hand-aligned today, codegen later.
- **PDF-native LLM input.** Claude accepts PDFs directly via base64 `document` blocks. No OCR, no fragile text extraction.
- **Provider abstraction.** [`LLMProvider`](apps/extractor/src/extractor/llm/base.py) is a runtime-checkable Protocol. `claude.py` (production), `openai.py` (stub demonstrating the swap is real), `fake.py` (deterministic tests). Selection is one env var.
- **Doc-type registry.** [`extractors.py`](apps/extractor/src/extractor/extractors.py) maps each `DocumentType` to its Pydantic schema and a short instruction prompt. Adding a new doc type is one row, no plumbing.
- **Repository pattern for storage.** [`apps/web/lib/repository.ts`](apps/web/lib/repository.ts) defines `BorrowerRepository`. Today it reads JSON; tomorrow it reads Postgres — the UI doesn't change.
- **Single-call novelty detection.** [`extract_with_novelty`](apps/extractor/src/extractor/llm/base.py) returns the typed schema *and* a list of novel-field hints in one round-trip. No double extraction cost.

## Trade-offs

See [`docs/design.md`](docs/design.md#trade-offs-and-known-limitations) for the full discussion. The headline ones:

- JSON-on-disk vs database — fine for a take-home, designed for swap.
- TS types hand-aligned vs codegen — faster ship, longer-term refactor.
- Single borrower in the corpus — pipeline is N>1, only one is exercised.
- No PDF viewer in the UI yet — provenance pills point at `(doc_id, page)`; the rendered-PDF-beside-extracted-fields view is the obvious next step.

## Reviewer's quick run

If you want to see it without setting up Anthropic:

```bash
cd apps/extractor && uv run pytest -v   # 35 tests pass without the network
cd ../web && pnpm install && pnpm build  # builds clean
```

The integration test exercises the full pipeline end-to-end with the `FakeProvider`. To see real LLM output, set `ANTHROPIC_API_KEY` and run `uv run extractor run --corpus ../../documents`.
