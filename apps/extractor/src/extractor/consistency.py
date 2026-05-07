"""Cross-document consistency checks.

Runs after per-doc extraction. Compares fields that should agree across
docs (subject property address, borrower SSN, loan ID, borrower-of-record)
and emits an `ExtractionFlag(kind=CONFLICT)` per disagreement.

The aggregator does not reconcile conflicts — it picks a primary value via
documented preference rules and surfaces the conflict via a flag. The UI
shows both. A human decides.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from extractor.schema import (
    BankStatementFields,
    ClosingDisclosureFields,
    DocumentType,
    ExtractionFlag,
    FlagKind,
    FlagSeverity,
    Form1008Fields,
    Form1040Fields,
    PaystubFields,
    TitleReportFields,
    W2Fields,
)


def detect_conflicts(
    extractions: list[tuple[str, DocumentType, Any]],
) -> list[ExtractionFlag]:
    """`extractions` is a list of (document_id, doc_type, fields) tuples.

    Each conflict becomes one flag. Flag bodies are JSON-serializable so
    the UI can render them without bespoke handlers.
    """
    flags: list[ExtractionFlag] = []
    flags.extend(_check_subject_property(extractions))
    flags.extend(_check_loan_ids(extractions))
    flags.extend(_check_ssns(extractions))
    flags.extend(_check_borrower_of_record(extractions))
    return flags


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------


def _check_subject_property(
    extractions: list[tuple[str, DocumentType, Any]],
) -> list[ExtractionFlag]:
    by_addr: dict[str, list[tuple[str, DocumentType]]] = defaultdict(list)
    for doc_id, doc_type, fields in extractions:
        if doc_type is DocumentType.CLOSING_DISCLOSURE and isinstance(fields, ClosingDisclosureFields):
            if fields.property_address:
                by_addr[_addr_key(fields.property_address)].append((doc_id, doc_type))
        elif doc_type is DocumentType.UNDERWRITING_TRANSMITTAL_1008 and isinstance(fields, Form1008Fields):
            if fields.property_address:
                by_addr[_addr_key(fields.property_address)].append((doc_id, doc_type))
        elif doc_type is DocumentType.TITLE_REPORT and isinstance(fields, TitleReportFields):
            if fields.property_address:
                by_addr[_addr_key(fields.property_address)].append((doc_id, doc_type))
    if len(by_addr) <= 1:
        return []
    return [
        ExtractionFlag(
            id=f"flag-{uuid4().hex[:8]}",
            kind=FlagKind.CONFLICT,
            severity=FlagSeverity.ERROR,
            summary=(
                f"Subject property address differs across {len(by_addr)} sources"
            ),
            details={
                "field": "subject_property.address",
                "values": [
                    {
                        "address": addr,
                        "documents": [
                            {"document_id": doc_id, "doc_type": dt.value}
                            for doc_id, dt in docs
                        ],
                    }
                    for addr, docs in by_addr.items()
                ],
            },
            documents=[doc_id for docs in by_addr.values() for doc_id, _ in docs],
            field_path="properties[subject].address",
            detected_at=datetime.utcnow(),
        )
    ]


def _check_loan_ids(
    extractions: list[tuple[str, DocumentType, Any]],
) -> list[ExtractionFlag]:
    by_loan_id: dict[str, list[tuple[str, DocumentType]]] = defaultdict(list)
    for doc_id, doc_type, fields in extractions:
        if doc_type is DocumentType.CLOSING_DISCLOSURE and isinstance(fields, ClosingDisclosureFields):
            if fields.loan_id:
                by_loan_id[fields.loan_id.strip()].append((doc_id, doc_type))
        elif doc_type is DocumentType.UNDERWRITING_TRANSMITTAL_1008 and isinstance(fields, Form1008Fields):
            if fields.seller_loan_number:
                by_loan_id[fields.seller_loan_number.strip()].append((doc_id, doc_type))
    if len(by_loan_id) <= 1:
        return []
    return [
        ExtractionFlag(
            id=f"flag-{uuid4().hex[:8]}",
            kind=FlagKind.CONFLICT,
            severity=FlagSeverity.WARN,
            summary=f"Loan ID differs across {len(by_loan_id)} sources",
            details={
                "field": "loan.loan_id",
                "values": [
                    {
                        "loan_id": loan_id,
                        "documents": [
                            {"document_id": d, "doc_type": dt.value}
                            for d, dt in docs
                        ],
                    }
                    for loan_id, docs in by_loan_id.items()
                ],
            },
            documents=[d for docs in by_loan_id.values() for d, _ in docs],
            field_path="loan.loan_id",
            detected_at=datetime.utcnow(),
        )
    ]


def _check_ssns(
    extractions: list[tuple[str, DocumentType, Any]],
) -> list[ExtractionFlag]:
    """Detect SSN drift for the SAME person across docs.

    Heuristic: group by lowercase normalized name. If a person has 2+
    distinct full SSNs (last-4 collisions don't count), flag it.
    """
    ssns_by_person: dict[str, dict[str, list[tuple[str, DocumentType]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    def add(name: str | None, ssn: str | None, doc_id: str, dt: DocumentType) -> None:
        if not name or not ssn:
            return
        if "x" in ssn.lower() or "*" in ssn:
            return  # masked — can't compare confidently
        ssns_by_person[name.strip().lower()][ssn.strip()].append((doc_id, dt))

    for doc_id, doc_type, fields in extractions:
        if isinstance(fields, W2Fields):
            add(fields.employee_name, fields.employee_ssn, doc_id, doc_type)
        elif isinstance(fields, Form1040Fields):
            add(fields.taxpayer_name, fields.taxpayer_ssn, doc_id, doc_type)
            add(fields.spouse_name, fields.spouse_ssn, doc_id, doc_type)
        elif isinstance(fields, Form1008Fields):
            add(fields.co_borrower_name, fields.co_borrower_ssn, doc_id, doc_type)

    flags: list[ExtractionFlag] = []
    for person, ssn_map in ssns_by_person.items():
        if len(ssn_map) <= 1:
            continue
        flags.append(
            ExtractionFlag(
                id=f"flag-{uuid4().hex[:8]}",
                kind=FlagKind.CONFLICT,
                severity=FlagSeverity.ERROR,
                summary=f"SSN differs across docs for {person.title()}",
                details={
                    "field": "identifiers.ssn",
                    "person": person.title(),
                    "values": [
                        {
                            "ssn": ssn,
                            "documents": [
                                {"document_id": d, "doc_type": dt.value}
                                for d, dt in docs
                            ],
                        }
                        for ssn, docs in ssn_map.items()
                    ],
                },
                documents=[d for docs in ssn_map.values() for d, _ in docs],
                field_path=f"identifiers.ssn[{person}]",
                detected_at=datetime.utcnow(),
            )
        )
    return flags


def _check_borrower_of_record(
    extractions: list[tuple[str, DocumentType, Any]],
) -> list[ExtractionFlag]:
    """If a title report's proposed insureds don't intersect the borrower
    set on the CD / 1008, the title report may be for a different
    transaction.
    """
    title_insureds: list[str] = []
    title_doc_id: str | None = None
    expected_borrowers: set[str] = set()
    other_docs: list[str] = []

    for doc_id, doc_type, fields in extractions:
        if doc_type is DocumentType.TITLE_REPORT and isinstance(fields, TitleReportFields):
            title_insureds = [n.strip().lower() for n in (fields.proposed_insureds or [])]
            title_doc_id = doc_id
        elif doc_type is DocumentType.CLOSING_DISCLOSURE and isinstance(fields, ClosingDisclosureFields):
            for n in fields.borrower_names or []:
                expected_borrowers.add(n.strip().lower())
            other_docs.append(doc_id)
        elif doc_type is DocumentType.UNDERWRITING_TRANSMITTAL_1008 and isinstance(fields, Form1008Fields):
            if fields.borrower_name:
                expected_borrowers.add(fields.borrower_name.strip().lower())
            if fields.co_borrower_name:
                expected_borrowers.add(fields.co_borrower_name.strip().lower())
            other_docs.append(doc_id)

    if not (title_doc_id and title_insureds and expected_borrowers):
        return []

    if any(_name_overlap(t, b) for t in title_insureds for b in expected_borrowers):
        return []

    return [
        ExtractionFlag(
            id=f"flag-{uuid4().hex[:8]}",
            kind=FlagKind.CONFLICT,
            severity=FlagSeverity.ERROR,
            summary=(
                "Title report's proposed insureds don't match the borrower set "
                "on the loan documents — title report may be for a different "
                "transaction."
            ),
            details={
                "title_insureds": title_insureds,
                "expected_borrowers": sorted(expected_borrowers),
            },
            documents=[title_doc_id, *other_docs],
            field_path="title_report.proposed_insureds",
            detected_at=datetime.utcnow(),
        )
    ]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _addr_key(addr: Any) -> str:
    """Normalize an Address to a comparison key. Whitespace and case
    insensitive; strips punctuation. Good enough for cross-doc matching.
    """
    parts = [
        getattr(addr, "line_1", "") or "",
        getattr(addr, "city", "") or "",
        getattr(addr, "state", "") or "",
        getattr(addr, "postal_code", "") or "",
    ]
    return " ".join(p.strip().lower() for p in parts if p)


def _name_overlap(a: str, b: str) -> bool:
    """Loose name match — any non-trivial word in common counts."""
    a_words = {w for w in a.split() if len(w) > 2}
    b_words = {w for w in b.split() if len(w) > 2}
    return bool(a_words & b_words)
