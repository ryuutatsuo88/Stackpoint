"""Deterministic provider for tests.

The pipeline depends on `LLMProvider`, never on `ClaudeProvider`. Tests
inject a `FakeProvider` seeded with canned responses and run the entire
pipeline end-to-end without touching the network.

Lookup is by `(filename, schema_name)` — keeps fixtures readable and lets a
single fake satisfy multiple per-doc-type extractors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from extractor.llm.base import (
    ExtractionWithNovelty,
    LLMResponse,
    LLMUsage,
    NovelFieldHint,
)


class FakeProvider:
    name: ClassVar[str] = "fake"

    def __init__(
        self,
        *,
        structured: dict[tuple[str, str], dict[str, Any]] | None = None,
        novelty: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        classifications: dict[str, tuple[str, float]] | None = None,
    ) -> None:
        self.model = "fake"
        self._structured: dict[tuple[str, str], dict[str, Any]] = structured or {}
        self._novelty: dict[tuple[str, str], list[dict[str, Any]]] = novelty or {}
        self._classifications: dict[str, tuple[str, float]] = classifications or {}
        self.calls: list[dict[str, Any]] = []
        """Append-only log of every call. Tests assert on this to verify
        the pipeline reached the LLM with the right inputs."""

    def extract_structured[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[T]:
        key = (pdf_path.name, schema.__name__)
        self.calls.append(
            {
                "method": "extract_structured",
                "filename": pdf_path.name,
                "schema": schema.__name__,
                "instructions": instructions,
                "system": system,
            }
        )
        if key not in self._structured:
            raise KeyError(
                f"FakeProvider has no fixture for {key}. "
                f"Available: {sorted(self._structured.keys())}"
            )
        parsed = schema.model_validate(self._structured[key])
        return LLMResponse[schema](  # type: ignore[valid-type]
            parsed=parsed,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
            raw=self._structured[key],
        )

    def extract_with_novelty[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[ExtractionWithNovelty[T]]:
        inner = self.extract_structured(
            pdf_path, schema, instructions, system=system, max_tokens=max_tokens
        )
        key = (pdf_path.name, schema.__name__)
        novel = [NovelFieldHint.model_validate(n) for n in self._novelty.get(key, [])]
        wrapped: ExtractionWithNovelty[T] = ExtractionWithNovelty(
            fields=inner.parsed,
            novel_fields=novel,
        )
        return LLMResponse[ExtractionWithNovelty[T]](
            parsed=wrapped,
            usage=inner.usage,
            raw={"fields": inner.raw, "novel_fields": [n.model_dump() for n in novel]},
        )

    def classify(
        self,
        pdf_path: Path,
        candidate_types: list[str],
        *,
        instructions: str = "",
    ) -> tuple[str, float]:
        self.calls.append(
            {
                "method": "classify",
                "filename": pdf_path.name,
                "candidates": candidate_types,
            }
        )
        if pdf_path.name not in self._classifications:
            return ("unknown", 0.0)
        return self._classifications[pdf_path.name]
