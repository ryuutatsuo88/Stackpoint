# Extractor

Python pipeline that reads PDFs from `documents/`, classifies them, extracts structured fields with an LLM, aggregates them into a single `Borrower` record, and writes JSON to `apps/web/data/output/`.

## Run

```bash
uv sync
uv run extractor run --corpus ../../documents
```

Requires `ANTHROPIC_API_KEY` in the project root `.env` (or environment).

## Test

```bash
uv run pytest
```

## Layout

```
src/extractor/
  cli.py            # entrypoint
  pipeline.py       # ingest → classify → extract → aggregate → write
  classify.py       # doc-type classifier
  schema.py         # Pydantic models — single source of truth
  novelty.py        # detects fields not in known schemas
  consistency.py    # cross-document conflict detection
  llm/
    base.py         # LLMProvider Protocol
    claude.py       # Anthropic implementation
    openai.py       # stub
    fake.py         # deterministic test provider
  extractors/
    __init__.py     # registry
    paystub.py      # one module per known doc type
    w2.py
    ...
tests/
```

See `docs/schema.md` for the canonical data model.
