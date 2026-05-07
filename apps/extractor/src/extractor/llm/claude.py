"""Anthropic Claude implementation of `LLMProvider`.

Notes:
- PDFs are sent natively as base64 `document` blocks. No OCR, no fragile
  text extraction.
- Adaptive thinking is enabled by default — Claude decides per-doc when the
  extraction warrants reasoning.
- `client.messages.parse()` returns a Pydantic instance directly when
  `output_format=schema` is passed. We rely on that rather than parsing
  JSON ourselves.
- Prompt caching: when `system` is provided, we render it as a cache-marked
  text block so repeated extractions over the same corpus reuse the prefix.

Defaults follow the user's `claude-api` skill guidance: `claude-opus-4-7`
with adaptive thinking. Override per-instance or via `LLM_MODEL`.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, ClassVar

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

from extractor.llm.base import (
    ExtractionWithNovelty,
    LLMResponse,
    LLMUsage,
    NovelFieldHint,
)


_CLASSIFY_SYSTEM = (
    "You are a document classifier for a loan-processing pipeline. "
    "Given a PDF and a list of candidate document types, identify which "
    "candidate best matches the PDF. Return only the exact candidate string "
    "and a confidence score in [0, 1]."
)


class _ClassifyResult(BaseModel):
    doc_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str | None = None


class ClaudeProvider:
    """Production provider. Requires `ANTHROPIC_API_KEY` in the environment
    or passed to `__init__`.
    """

    name: ClassVar[str] = "claude"

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        api_key: str | None = None,
        *,
        max_tokens_default: int = 16_000,
    ) -> None:
        self.model = model
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self._max_tokens_default = max_tokens_default

    # ------------------------------------------------------------------
    # core methods
    # ------------------------------------------------------------------

    def extract_structured[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[T]:
        return self._parse(pdf_path, schema, instructions, system=system, max_tokens=max_tokens)

    def extract_with_novelty[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[ExtractionWithNovelty[T]]:
        wrapper = _make_novelty_wrapper(schema)
        novelty_instructions = (
            f"{instructions}\n\n"
            "After populating `fields`, list every structured datum you saw "
            "in the document that isn't represented in the `fields` schema. "
            "Put each in `novel_fields` with a snake_case name, a sample "
            "value (≤200 chars), a suggested primitive type, and brief "
            "notes about where it appeared. If everything fit the schema, "
            "return `novel_fields: []`."
        )
        return self._parse(
            pdf_path,
            wrapper,
            novelty_instructions,
            system=system,
            max_tokens=max_tokens,
        )

    def classify(
        self,
        pdf_path: Path,
        candidate_types: list[str],
        *,
        instructions: str = "",
    ) -> tuple[str, float]:
        prompt = (
            f"Candidate document types: {', '.join(candidate_types)}.\n"
            "If none of the candidates fit, return 'unknown' with a low "
            "confidence. Use the document's content, not the filename.\n"
            f"{instructions}"
        ).strip()
        result = self._parse(
            pdf_path,
            _ClassifyResult,
            prompt,
            system=_CLASSIFY_SYSTEM,
            max_tokens=2048,
        )
        return result.parsed.doc_type, result.parsed.confidence

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _parse[T: BaseModel](
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None,
        max_tokens: int,
    ) -> LLMResponse[T]:
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "output_format": schema,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        _pdf_block(pdf_path),
                        {"type": "text", "text": instructions},
                    ],
                }
            ],
        }
        if system:
            request_kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        response = self.client.messages.parse(**request_kwargs)

        if response.parsed_output is None:
            raise ValidationError.from_exception_data(
                title=schema.__name__,
                line_errors=[
                    {
                        "type": "value_error",
                        "loc": ("__root__",),
                        "msg": f"Model returned non-parseable output. stop_reason={response.stop_reason}",
                        "input": None,
                    }
                ],
            )

        usage = response.usage
        return LLMResponse[schema](  # type: ignore[valid-type]
            parsed=response.parsed_output,
            usage=LLMUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
            raw=response.model_dump(mode="json"),
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _pdf_block(path: Path) -> dict[str, Any]:
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": data,
        },
    }


def _make_novelty_wrapper[T: BaseModel](schema: type[T]) -> type[ExtractionWithNovelty[T]]:
    """Build a Pydantic class binding `ExtractionWithNovelty` to `schema`.

    `client.messages.parse()` infers the JSON Schema from this class, so we
    need a concrete bound type rather than the generic alias.
    """
    name = f"ExtractionWithNovelty_{schema.__name__}"

    class Bound(BaseModel):
        fields: schema  # type: ignore[valid-type]
        novel_fields: list[NovelFieldHint] = Field(default_factory=list)

    Bound.__name__ = name
    Bound.__qualname__ = name
    return Bound  # type: ignore[return-value]
