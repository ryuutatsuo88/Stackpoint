"""Provider selection — env-var-driven, used by the CLI."""

from __future__ import annotations

import os

from extractor.llm.base import LLMProvider


def get_provider(
    name: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Return a configured provider. Reads `LLM_PROVIDER` and `LLM_MODEL`
    from the environment when arguments are omitted.
    """
    resolved_name = name or os.getenv("LLM_PROVIDER", "claude")
    resolved_model = model or os.getenv("LLM_MODEL")

    if resolved_name == "claude":
        from extractor.llm.claude import ClaudeProvider

        return ClaudeProvider(model=resolved_model or "claude-opus-4-7")
    if resolved_name == "openai":
        from extractor.llm.openai import OpenAIProvider

        return OpenAIProvider(model=resolved_model or "gpt-5")
    if resolved_name == "fake":
        raise ValueError(
            "The 'fake' provider exists for tests; instantiate FakeProvider "
            "directly with seeded fixtures."
        )
    raise ValueError(f"Unknown LLM provider: {resolved_name!r}")
