# `apps/` — quick start

Two apps: the Python extractor and the Next.js web UI. They communicate through JSON files at `apps/web/data/output/`.

## `apps/extractor/`

```bash
uv sync                                      # install
uv run pytest                                # 35 tests, no network needed
uv run extractor run --corpus ../../documents
```

Layout (in dependency order):

```
src/extractor/
  schema.py        Pydantic models — source of truth
  llm/             LLMProvider Protocol + Claude / OpenAI stub / Fake
  classify.py      filename heuristic + LLM verify
  extractors.py    DocumentType → (schema, prompt) registry
  consistency.py   cross-doc conflict checks
  aggregator.py    per-doc fields → single Borrower record
  pipeline.py      orchestrator
  cli.py           `extractor run` entrypoint
```

See `apps/extractor/README.md` for more.

## `apps/web/`

```bash
pnpm install
pnpm dev        # http://localhost:3000
pnpm build      # production build
pnpm typecheck
pnpm test       # vitest
pnpm exec playwright test   # if Playwright browsers installed
```

Routes:

- `/` — borrower list
- `/borrowers/[id]` — full record with provenance
- `/flags` — cross-borrower flag review queue

## Why two apps and not one

- **Different runtimes.** Python is the right tool for LLM extraction with Pydantic; Next.js is the right tool for a polished UI.
- **Independently deployable.** The pipeline can run on a schedule (or in response to S3 uploads, or whatever); the UI is a stateless web app reading from durable storage.
- **Different blast radii.** A bug in extraction logic doesn't take the UI down. A redeploy of the UI doesn't reprocess any documents.
