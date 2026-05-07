"""LLM provider abstraction.

The pipeline depends on the `LLMProvider` Protocol, never on a concrete
implementation. Swapping providers is a one-env-var change.
"""

from extractor.llm.base import (
    ExtractionWithNovelty,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    NovelFieldHint,
)
from extractor.llm.factory import get_provider

__all__ = [
    "ExtractionWithNovelty",
    "LLMProvider",
    "LLMResponse",
    "LLMUsage",
    "NovelFieldHint",
    "get_provider",
]
