# Task Tracker

This file is the single source of truth for what's left. The `/loop` prompt picks the next unchecked task whose dependencies are satisfied, executes it, marks it `[x]` with a one-line note, and exits when nothing remains.

Convention:
- `[ ]` = pending
- `[~]` = in progress
- `[x]` = done — append `→ note` for what was actually done.
- `[!]` = blocked — append `→ blocker` describing what's needed to unblock.

## Phase 0 — Foundations

- [x] Scaffold repo: `apps/`, `docs/`, rename `assignment_documents/` → `documents/`, .gitignore, .env.example, root README skeleton → done in initial commit; `.env` gitignored.
- [~] Walk corpus and produce `docs/schema.md` — per-doc-type field map driving the Pydantic model.
- [~] `docs/requirements.md` written; `docs/tasks.md` (this file) initialized.

## Phase 1 — Python extractor

- [ ] `apps/extractor` bootstrap with uv: `pyproject.toml`, src layout, ruff + mypy + pytest configured.
- [ ] `schema.py` — Pydantic models: `Borrower`, `IncomeRecord`, `Account`, `Loan`, `Document`, `Provenance`, `ExtractionFlag`. Export JSON Schema.
- [ ] `llm/base.py` — `LLMProvider` Protocol with `extract_structured(pdf_path, schema, prompt) -> dict` and `complete(prompt) -> str`.
- [ ] `llm/claude.py` — Anthropic SDK, sends PDFs natively, uses prompt caching, returns structured JSON.
- [ ] `llm/openai.py` — stub showing the same interface fits.
- [ ] `llm/fake.py` — deterministic provider for tests; reads canned responses from a fixtures dir.
- [ ] `classify.py` — filename heuristic + cheap LLM verification → returns one of {paystub, w2, form_1040, evoe, bank_statement_checking, bank_statement_savings, closing_disclosure, title_report, letter_of_explanation, unknown}.
- [ ] Per-doc extractors under `extractors/` — one module per known doc type, each owning its prompt + the slice of the schema it produces.
- [ ] `aggregator.py` — merge per-doc outputs into one `Borrower` with provenance preserved; reconcile income across paystub/W2/1040/EVOE without prematurely collapsing.
- [ ] `novelty.py` — diff per-doc fields vs schema; emit `ExtractionFlag` for novel fields.
- [ ] `pipeline.py` + `cli.py` — `extractor run --corpus <path>` end-to-end orchestration.
- [ ] Pytest: schema validation, classifier, novelty diff, aggregator merge logic; integration test runs the pipeline against fixtures with the fake provider.

## Phase 2 — Web app

- [ ] `apps/web` scaffold: Next.js 15 + TS + Tailwind, App Router, dark navy theme tokens.
- [ ] `lib/types.ts` — types generated from JSON Schema (or hand-written matching schema; pick the lighter path).
- [ ] `lib/repository.ts` — `BorrowerRepository` interface; JSON-on-disk implementation reads from `apps/web/data/output/`.
- [ ] `/` — borrowers list, polished card layout.
- [ ] `/borrowers/[id]` — full record: PII, income history (chart + table), accounts, loan, source-doc list.
- [ ] `/borrowers/[id]/documents/[docId]` — PDF embed beside extracted fields with provenance highlighted.
- [ ] `/flags` — novel-field review queue.
- [ ] Vitest unit tests for the data layer + a representative component.
- [ ] Playwright e2e: home → borrower → income history → open source doc.

## Phase 3 — Docs and polish

- [ ] `docs/design.md` — architecture overview, mermaid component diagram, data flow, trade-offs, how-to-add-a-new-doc-type recipe, known limitations, what-I'd-do-with-more-time.
- [ ] Final `README.md` pass — matches what actually ships.
- [ ] `apps/README.md` — quick-start specifically for `apps/`.
- [ ] Smoke run end-to-end on a clean checkout to verify the README is correct.
