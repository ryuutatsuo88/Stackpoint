"""OpenAI provider stub.

Demonstrates that the `LLMProvider` Protocol is genuinely provider-neutral.
Implementing this fully is a one-file PR: swap the SDK calls in
`claude.py` for the OpenAI Responses API + Files API, keep the same
return types.

Why a stub instead of a full implementation? OpenAI's PDF handling differs
(Files API + file_id reference, not native base64 document blocks), and a
real implementation needs its own prompt-tuning pass — out of scope for
this take-home. The stub raises `NotImplementedError` with a pointer.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from extractor.llm.base import ExtractionWithNovelty, LLMResponse


class OpenAIProvider:
    name: ClassVar[str] = "openai"

    def __init__(self, model: str = "gpt-5", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key

    def extract_structured[T: BaseModel](  # noqa: ARG002
        self,
        pdf_path: Path,
        schema: type[T],
        instructions: str,
        *,
        system: str | None = None,
        max_tokens: int = 16_000,
    ) -> LLMResponse[T]:
        raise NotImplementedError(
            "OpenAIProvider is a stub. To implement: use the OpenAI Responses "
            "API with `response_format={'type': 'json_schema', 'schema': ...}`, "
            "upload PDFs via the Files API, and reference file_id in the "
            "input. Map the response back into LLMResponse[T] the same way "
            "claude.py does."
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
        raise NotImplementedError("see extract_structured")

    def classify(
        self,
        pdf_path: Path,
        candidate_types: list[str],
        *,
        instructions: str = "",
    ) -> tuple[str, float]:
        raise NotImplementedError("see extract_structured")
