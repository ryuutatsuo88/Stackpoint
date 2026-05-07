"""Schema smoke tests.

These don't replace the full unit suite that comes later — they exist so
schema breakages surface in CI before the rest of the pipeline tries to
build on top of a broken contract.
"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from extractor.schema import (
    Account,
    AccountKind,
    Address,
    Borrower,
    BorrowerIdentifiers,
    Document,
    DocumentType,
    ExtractionFlag,
    ExtractionMeta,
    FlagKind,
    FlagSeverity,
    MultiSourced,
    PII,
    Provenance,
    Sourced,
    borrower_json_schema,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _prov(doc_id: str = "doc-1", page: int = 1, conf: float = 0.95) -> Provenance:
    return Provenance(document_id=doc_id, page=page, confidence=conf)


def _sourced[T](value: T) -> Sourced[T]:
    return Sourced[type(value)](value=value, provenance=_prov())  # type: ignore[valid-type]


def _multi[T](primary: T, *alternates: T) -> MultiSourced[T]:
    return MultiSourced[type(primary)](  # type: ignore[valid-type]
        primary=Sourced[type(primary)](value=primary, provenance=_prov("doc-1")),  # type: ignore[valid-type]
        alternates=[
            Sourced[type(primary)](value=alt, provenance=_prov(f"doc-{i+2}"))  # type: ignore[valid-type]
            for i, alt in enumerate(alternates)
        ],
    )


@pytest.fixture
def address() -> Address:
    return Address(
        line_1="175 13th Street",
        city="Washington",
        state="DC",
        postal_code="20013",
    )


@pytest.fixture
def minimal_borrower(address: Address) -> Borrower:
    pii = PII(
        legal_name=_multi("John Homeowner"),
        address=_multi(address),
    )
    return Borrower(
        id="loan-214",
        pii=pii,
        identifiers=BorrowerIdentifiers(
            ssn=_multi("999-40-5000"),
        ),
        extraction_meta=ExtractionMeta(
            extracted_at=datetime(2026, 5, 6, 22, 0, 0),
            extractor_version="0.1.0",
            llm_provider="claude",
            llm_model="claude-sonnet-4-6",
            corpus_path="documents/Loan Documents/Loan 214",
            duration_seconds=1.0,
        ),
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_confidence_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(document_id="d", page=1, confidence=1.5)

    def test_page_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(document_id="d", page=0, confidence=0.5)


class TestMultiSourced:
    def test_alternates_default_to_empty(self, address: Address) -> None:
        m = MultiSourced[Address](
            primary=Sourced[Address](value=address, provenance=_prov()),
        )
        assert m.alternates == []

    def test_carries_provenance_for_each_alternate(self) -> None:
        m = _multi("John Homeowner", "John H Homeowner", "JOHN HOMEOWNER")
        assert m.primary.value == "John Homeowner"
        assert {alt.value for alt in m.alternates} == {"John H Homeowner", "JOHN HOMEOWNER"}
        assert all(alt.provenance.confidence > 0 for alt in m.alternates)


class TestBorrower:
    def test_minimal_borrower_validates(self, minimal_borrower: Borrower) -> None:
        # Round-trip via JSON to make sure all the generic types serialize.
        dumped = minimal_borrower.model_dump_json()
        rehydrated = Borrower.model_validate_json(dumped)
        assert rehydrated.id == "loan-214"
        assert rehydrated.pii.legal_name.primary.value == "John Homeowner"

    def test_can_attach_flags(self, minimal_borrower: Borrower) -> None:
        flag = ExtractionFlag(
            id="flag-001",
            kind=FlagKind.CONFLICT,
            severity=FlagSeverity.WARN,
            summary="Subject property address differs across CD and 1008.",
            documents=["doc-cd", "doc-1008"],
            field_path="properties[0].address",
            detected_at=datetime(2026, 5, 6, 22, 5, 0),
        )
        b = minimal_borrower.model_copy(update={"flags": [flag]})
        assert b.flags[0].kind == FlagKind.CONFLICT


class TestAccount:
    def test_account_construction(self, address: Address) -> None:
        acct = Account(
            institution_name=_sourced("Sandy Springs Credit Union"),
            kind=AccountKind.CHECKING,
            account_number=_sourced("123456789"),
            holders=["John Homeowner", "Mary Homeowner"],
            statement_period_start=date(2025, 4, 1),
            statement_period_end=date(2025, 4, 30),
        )
        assert acct.kind is AccountKind.CHECKING
        assert acct.institution_name.value == "Sandy Springs Credit Union"


class TestDocument:
    def test_unknown_doc_type_is_allowed(self) -> None:
        doc = Document(
            id="doc-1",
            path="documents/Loan Documents/Loan 214/document.pdf",
            filename="document.pdf",
            page_count=4,
            sha256="abc123",
            doc_type=DocumentType.UNKNOWN,
            classifier_confidence=0.4,
            extracted_at=datetime(2026, 5, 6, 22, 0, 0),
            bytes=92426,
        )
        assert doc.doc_type is DocumentType.UNKNOWN


class TestJsonSchemaExport:
    def test_schema_generation_succeeds(self) -> None:
        schema = borrower_json_schema()
        assert "$defs" in schema
        assert schema["properties"]["id"]["type"] == "string"

    def test_known_doc_types_appear_in_enum(self) -> None:
        schema = borrower_json_schema()
        doc_type_def = schema["$defs"]["DocumentType"]
        assert "underwriting_transmittal_1008" in doc_type_def["enum"]
