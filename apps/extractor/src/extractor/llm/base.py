"""Provider-neutral types and the `LLMProvider` Protocol.

The Protocol uses structural typing — a class is an `LLMProvider` if it has
the right methods, no inheritance required. The Anthropic / OpenAI / fake
providers all satisfy it independently.

`extract_structured` returns a typed Pydantic model (the doc-type schema).
`extract_with_novelty` returns the same plus a list of novel fields the
model spotted that aren't in the schema — drives the schema-evolution
detection without a second LLM round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    """Token accounting for one LLM call. Cache fields default to 0 for
    providers that don't expose prompt caching.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMResponse[T: BaseModel](BaseModel):
    """A successful structured extraction. `parsed` is the Pydantic model
    instance; `usage` is for cost tracking and tests; `raw` is kept for
    debugging extraction failures.
    """

    parsed: T
    usage: LLMUsage
    raw: dict[str, Any] = Field(default_factory=dict)


class NovelFieldHint(BaseModel):
    """A field the LLM observed in the document that isn't in the canonical
    schema. The aggregator turns these into `ExtractionFlag`s for review.
    """

    field_name: str
    """snake_case name suggested by the LLM."""

    sample_value: str
    """First observed value, truncated to ~200 chars. PII gets redacted at
    the aggregator level, not here — keep raw for now."""

    suggested_type: Literal["str", "int", "float", "bool", "date", "list", "object"]
    notes: str | None = None


class ExtractionWithNovelty[T: BaseModel](BaseModel):
    fields: T
    novel_fields: list[NovelFieldHint] = Field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can extract structured data from a PDF.

    Implementations:
      - `claude.ClaudeProvider`   — production
      - `openai.OpenAIProvider`   — stub showing the interface fits
      - `fake.FakeProvider`       — deterministic, used by tests
    """

    name: str
    """Short identifier for telemetry, e.g. 'claude' / 'openai' / 'fake'."""

    model: str

    def extract_structured[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[T]:
        """Extract fields from `pdf_path` into an instance of `schema`."""
        ...

    def extract_with_novelty[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[ExtractionWithNovelty[T]]:
        """Same as `extract_structured` but also asks the model for any
        structured fields it noticed that aren't in `schema`. Single call —
        avoids paying for the doc twice.
        """
        ...

    def classify(
        self,
        pdf_path: Path,
        candidate_types: list[str],
        *,
        instructions: str = "",
    ) -> tuple[str, float]:
        """Best-fit doc type from `candidate_types` plus a confidence in [0, 1]."""
        ...
