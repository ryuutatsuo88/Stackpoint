"""LLM provider tests.

We don't hit the network. The Claude and OpenAI providers are tested only
for Protocol satisfaction and for the cheap behaviors that don't require an
API key (factory wiring, NotImplementedError surface). The FakeProvider
gets a full functional test because the rest of the pipeline depends on
it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

from extractor.llm import (
    ExtractionWithNovelty,
    LLMProvider,
    NovelFieldHint,
    get_provider,
)
from extractor.llm.claude import ClaudeProvider
from extractor.llm.fake import FakeProvider
from extractor.llm.openai import OpenAIProvider


class ToyFields(BaseModel):
    name: str
    amount: float
    period_end: date


@pytest.fixture
def pdf_path(tmp_path: Path) -> Path:
    p = tmp_path / "Paystub- John Homeowner (Current).pdf"
    p.write_bytes(b"%PDF-1.4 fake bytes")
    return p


class TestProtocolSatisfaction:
    def test_claude_satisfies_protocol(self) -> None:
        # No network call — just construction. Anthropic() with a fake key
        # is fine until you call .messages.create().
        provider = ClaudeProvider(model="claude-opus-4-7", api_key="sk-test")
        assert isinstance(provider, LLMProvider)
        assert provider.name == "claude"

    def test_openai_satisfies_protocol(self) -> None:
        provider = OpenAIProvider(api_key="sk-test")
        assert isinstance(provider, LLMProvider)
        assert provider.name == "openai"

    def test_fake_satisfies_protocol(self) -> None:
        assert isinstance(FakeProvider(), LLMProvider)


class TestFactory:
    def test_returns_claude_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        provider = get_provider()
        assert isinstance(provider, ClaudeProvider)
        assert provider.model == "claude-opus-4-7"

    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-5-turbo")
        provider = get_provider()
        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-5-turbo"

    def test_fake_must_be_built_directly(self) -> None:
        with pytest.raises(ValueError, match="instantiate FakeProvider directly"):
            get_provider("fake")

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("anthropic-but-misspelled")


class TestOpenAIStub:
    def test_extract_raises_with_pointer(self, pdf_path: Path) -> None:
        provider = OpenAIProvider()
        with pytest.raises(NotImplementedError, match="OpenAIProvider is a stub"):
            provider.extract_structured(pdf_path, ToyFields, "extract")


class TestFakeProvider:
    def test_returns_seeded_fields(self, pdf_path: Path) -> None:
        provider = FakeProvider(
            structured={
                ("Paystub- John Homeowner (Current).pdf", "ToyFields"): {
                    "name": "John Homeowner",
                    "amount": 3377.21,
                    "period_end": "2025-04-15",
                },
            }
        )
        result = provider.extract_structured(pdf_path, ToyFields, "extract")
        assert result.parsed.name == "John Homeowner"
        assert result.parsed.amount == 3377.21
        assert result.parsed.period_end == date(2025, 4, 15)
        assert result.usage.input_tokens > 0

    def test_missing_fixture_raises_helpful_keyerror(self, pdf_path: Path) -> None:
        provider = FakeProvider()
        with pytest.raises(KeyError, match="no fixture"):
            provider.extract_structured(pdf_path, ToyFields, "extract")

    def test_logs_calls_for_assertions(self, pdf_path: Path) -> None:
        provider = FakeProvider(
            structured={
                ("Paystub- John Homeowner (Current).pdf", "ToyFields"): {
                    "name": "x",
                    "amount": 0.0,
                    "period_end": "2025-01-01",
                },
            }
        )
        provider.extract_structured(pdf_path, ToyFields, "extract", system="hello")
        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "extract_structured"
        assert call["filename"] == "Paystub- John Homeowner (Current).pdf"
        assert call["schema"] == "ToyFields"
        assert call["system"] == "hello"

    def test_extract_with_novelty_returns_wrapped(self, pdf_path: Path) -> None:
        provider = FakeProvider(
            structured={
                ("Paystub- John Homeowner (Current).pdf", "ToyFields"): {
                    "name": "John",
                    "amount": 100.0,
                    "period_end": "2025-04-15",
                },
            },
            novelty={
                ("Paystub- John Homeowner (Current).pdf", "ToyFields"): [
                    {
                        "field_name": "advice_number",
                        "sample_value": "00000123",
                        "suggested_type": "str",
                        "notes": "appears top-right of header",
                    },
                ],
            },
        )
        result = provider.extract_with_novelty(pdf_path, ToyFields, "extract")
        assert isinstance(result.parsed, ExtractionWithNovelty)
        assert result.parsed.fields.name == "John"
        assert len(result.parsed.novel_fields) == 1
        novel = result.parsed.novel_fields[0]
        assert isinstance(novel, NovelFieldHint)
        assert novel.field_name == "advice_number"

    def test_classify_returns_seeded(self, pdf_path: Path) -> None:
        provider = FakeProvider(
            classifications={"Paystub- John Homeowner (Current).pdf": ("paystub", 0.97)}
        )
        doc_type, confidence = provider.classify(pdf_path, ["paystub", "w2", "evoe"])
        assert doc_type == "paystub"
        assert confidence == 0.97

    def test_classify_unknown_when_unseeded(self, pdf_path: Path) -> None:
        provider = FakeProvider()
        doc_type, confidence = provider.classify(pdf_path, ["paystub"])
        assert doc_type == "unknown"
        assert confidence == 0.0
