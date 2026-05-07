"""Per-doc-type extractors as a registry.

Each entry binds a `DocumentType` to a strict-typed Pydantic schema and a
short instruction prompt. The pipeline looks the doc type up in `REGISTRY`
and dispatches to a single `extract` function — no per-doc-type module
sprawl. Adding a new doc type = adding a row.

Prompts are deliberately short. The schema's field names and descriptions
do most of the work; the prompt only adds doc-specific guidance the
schema can't express (e.g. "two tax years are stacked in one PDF, return
the most recent").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from extractor.llm.base import LLMProvider, LLMResponse
from extractor.schema import (
    BankStatementFields,
    ClosingDisclosureFields,
    DocumentType,
    EvoeFields,
    Form1008Fields,
    Form1040Fields,
    LetterOfExplanationFields,
    PaystubFields,
    ScheduleCFields,
    TitleReportFields,
    W2Fields,
)


_SHARED_SYSTEM = (
    "You are a precise extraction system for residential mortgage documents. "
    "Read the attached PDF and populate the requested schema. Use only "
    "values that appear in the document — never infer or fabricate. If a "
    "field isn't present, omit it (let the schema use its default) rather "
    "than guessing. Dates must be parseable; normalize to YYYY-MM-DD. "
    "Numbers must be numeric (no $ or commas)."
)


@dataclass(frozen=True)
class _Extractor:
    schema: type[BaseModel]
    instructions: str


REGISTRY: dict[DocumentType, _Extractor] = {
    DocumentType.PAYSTUB: _Extractor(
        schema=PaystubFields,
        instructions=(
            "Extract the paystub. `gross_pay_current` is the current period's "
            "gross; `gross_pay_ytd` is year-to-date. Capture deductions split "
            "current vs YTD where shown. If a deposit account number is masked "
            "(****1234), keep the masked form."
        ),
    ),
    DocumentType.W2: _Extractor(
        schema=W2Fields,
        instructions=(
            "Extract the W-2. Use the box numbers as the source of truth — "
            "the form's positional layout is unreliable. Box 12 is a list "
            "of (code, amount) pairs; include every populated row."
        ),
    ),
    DocumentType.EVOE: _Extractor(
        schema=EvoeFields,
        instructions=(
            "Extract the verification of employment. The annual income table "
            "spans multiple years; mark `is_year_to_date=true` for partial-"
            "year rows."
        ),
    ),
    DocumentType.FORM_1040: _Extractor(
        schema=Form1040Fields,
        instructions=(
            "Extract Form 1040. **If the PDF contains multiple tax years, "
            "extract the MOST RECENT (highest tax_year) only.** Lines 1a, "
            "1z, 8, 9, 11, 12, 15, 24, 33 are the priorities."
        ),
    ),
    DocumentType.SCHEDULE_C: _Extractor(
        schema=ScheduleCFields,
        instructions=(
            "Extract Schedule C. **If the PDF contains multiple tax years, "
            "extract the MOST RECENT (highest tax_year) only.** Net profit "
            "(line 31) is the headline figure for underwriting."
        ),
    ),
    DocumentType.BANK_STATEMENT_CHECKING: _Extractor(
        schema=BankStatementFields,
        instructions=(
            "Extract the checking statement. Transaction descriptions may "
            "span multiple lines in the source — join them. Capture every "
            "transaction row."
        ),
    ),
    DocumentType.BANK_STATEMENT_SAVINGS: _Extractor(
        schema=BankStatementFields,
        instructions=(
            "Extract the savings statement. Disclosure / boilerplate pages "
            "have no transactions — skip them."
        ),
    ),
    DocumentType.CLOSING_DISCLOSURE: _Extractor(
        schema=ClosingDisclosureFields,
        instructions=(
            "Extract the closing disclosure. This corpus may contain "
            "partial / non-CFPB-standard CDs — extract whatever is "
            "present, omit anything that isn't."
        ),
    ),
    DocumentType.TITLE_REPORT: _Extractor(
        schema=TitleReportFields,
        instructions=(
            "Extract from the ALTA Title Commitment. Schedule A holds the "
            "core fields (insureds, property address, commitment number, "
            "policies). Skip boilerplate definitions on early pages."
        ),
    ),
    DocumentType.LETTER_OF_EXPLANATION: _Extractor(
        schema=LetterOfExplanationFields,
        instructions=(
            "Extract the letter of explanation. `subject_topic` is a brief "
            "label for what's being explained (e.g. 'recent credit "
            "inquiry'). `referenced_event_date` is the date of the event "
            "being explained, NOT the letter's date."
        ),
    ),
    DocumentType.UNDERWRITING_TRANSMITTAL_1008: _Extractor(
        schema=Form1008Fields,
        instructions=(
            "Extract from the Fannie Form 1008 (Uniform Underwriting "
            "Transmittal Summary). Many fields are checkbox-style; map "
            "checkmark glyphs (✘ / X) to a single string per labeled box. "
            "Use the values from the Form 1008 page — the Conditional "
            "Approval cover page reuses the same labels with different "
            "phrasings."
        ),
    ),
}


def supported_doc_types() -> set[DocumentType]:
    return set(REGISTRY.keys())


def extract(
    doc_type: DocumentType,
    pdf_path: Path,
    provider: LLMProvider,
    *,
    with_novelty: bool = True,
) -> LLMResponse[Any]:
    """Run the registered extractor for `doc_type` on `pdf_path`."""
    if doc_type not in REGISTRY:
        raise ValueError(f"No extractor registered for {doc_type}")
    entry = REGISTRY[doc_type]
    if with_novelty:
        return provider.extract_with_novelty(
            pdf_path,
            entry.schema,
            entry.instructions,
            system=_SHARED_SYSTEM,
        )
    return provider.extract_structured(
        pdf_path,
        entry.schema,
        entry.instructions,
        system=_SHARED_SYSTEM,
    )
