# Requirements

Source: take-home email from Stackpoint, received 2026-05-06. Deadline: 7 days (2026-05-13). User opted to start immediately rather than coast on the deadline.

## Goal

Build an unstructured-data extraction system over a provided document corpus. Full autonomy on stack and approach. Evaluators care about reasoning and trade-offs more than a single "right" solution.

## Corpus chosen

**Loan Documents** — `documents/Loan Documents/Loan 214/` (10 PDFs, single borrower folder).

> **Required output (verbatim from the brief):** "produce a structured record for each borrower that includes extracted PII like their name, address, full income history, and associated account/loan numbers, with a clear reference to the original document(s) from which the information was sourced."

## Deliverables

1. **System Design Document** — markdown (`docs/design.md`), with architecture overview and a component diagram.
2. **Working Implementation**
   - Document ingestion pipeline.
   - Extraction logic using AI/LLM tooling.
   - Basic query or retrieval interface.
   - Test coverage for critical paths (encouraged).
3. **README** — setup/run instructions and a summary of architectural and implementation decisions.

## Self-imposed scope (agreed with user)

- **Stack:** Python (uv) extractor + Next.js 15 (TypeScript, App Router, Tailwind) UI. Storage = JSON files on disk, accessed via a repository interface so swapping for a real DB is one file.
- **LLM:** Claude (default) behind a replaceable `LLMProvider` Protocol. OpenAI stub included to demonstrate the swap is real. Fake provider for deterministic tests.
- **Polish bar:** "Airbnb-grade" UI, dark navy theme.
- **Tests:** unit (pytest, vitest), integration (pipeline end-to-end with fake LLM), e2e (Playwright golden path).
- **Schema evolution:** novel-field detector flags structured fields the LLM finds outside the canonical schema; the UI exposes a `/flags` page for human review.
- **Provenance:** every extracted field carries `{source_path, page, confidence}` and the UI renders the original PDF beside the structured value.

## Explicitly out of scope

- Multi-tenant auth / user accounts.
- Real database, hosted deployment, CI/CD beyond what runs locally.
- OCR — Claude accepts PDFs directly and the corpus appears to be born-digital.
- Multi-borrower support beyond what the data model already permits (the corpus is N=1; the system is designed for N>1 but only one record is produced).

## Success criteria

- A reviewer can `cp .env.example .env`, drop in an Anthropic key, run two commands, and see structured borrower data in a polished UI within ~5 minutes.
- Every extracted field on the borrower page is traceable to its source PDF and page.
- Tests run green.
- Adding a new doc type is a recipe in the design doc, not a refactor.
