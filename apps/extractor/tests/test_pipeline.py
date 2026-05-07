"""End-to-end pipeline integration test.

Runs the full pipeline against a synthetic corpus with the FakeProvider.
Verifies the headline behaviors that distinguish this system: provenance,
multi-source merging, cross-doc consistency flags, and novel-field flags.

If this test passes, the same code path will work against the real
ClaudeProvider — only the LLM I/O differs. Real-LLM verification is a
separate, manual step (see README).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extractor.llm.fake import FakeProvider
from extractor.pipeline import run_borrower
from extractor.schema import Borrower, FlagKind


def test_runs_end_to_end(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"

    borrower, output_path = run_borrower(
        folder, fake_provider_loan_214, output_dir=output_dir
    )

    assert output_path.exists()
    rehydrated = Borrower.model_validate_json(output_path.read_text())
    assert rehydrated.id == "loan-214"


def test_legal_name_picks_1040_over_paystub(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    """Preference rule: 1040 → W-2 → EVOE → ... → paystub. The 1040 entry
    in our fixtures says 'John Homeowner' (same as paystub), so we can't
    distinguish on value — but we CAN check the primary's source doc.
    """
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    primary_doc_id = borrower.pii.legal_name.primary.provenance.document_id
    primary_doc = next(d for d in borrower.source_documents if d.id == primary_doc_id)
    assert primary_doc.doc_type.value == "form_1040"


def test_emits_subject_property_conflict_flag(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    conflicts = [f for f in borrower.flags if f.kind is FlagKind.CONFLICT]
    summaries = " | ".join(f.summary for f in conflicts)
    assert "Subject property address differs" in summaries


def test_emits_loan_id_conflict_flag(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    conflicts = [f for f in borrower.flags if f.kind is FlagKind.CONFLICT]
    summaries = " | ".join(f.summary for f in conflicts)
    assert "Loan ID differs" in summaries


def test_emits_borrower_of_record_conflict(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    """Title report's proposed insureds (VanAssens) don't intersect the
    borrower set on the CD/1008 (Homeowners). System should flag.
    """
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    summaries = " | ".join(f.summary for f in borrower.flags if f.kind is FlagKind.CONFLICT)
    assert "proposed insureds don't match" in summaries


def test_emits_novel_field_flag(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    novel = [f for f in borrower.flags if f.kind is FlagKind.NOVEL_FIELD]
    assert any(f.details.get("field_name") == "advice_number" for f in novel)


def test_income_records_have_provenance(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    assert len(borrower.income) > 0
    for income in borrower.income:
        assert income.amount.provenance.document_id
        assert income.amount.provenance.page >= 1
        assert 0.0 <= income.amount.provenance.confidence <= 1.0


def test_accounts_built_from_bank_statements(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    kinds = {a.kind for a in borrower.accounts}
    assert "checking" in {k.value for k in kinds}
    assert "savings" in {k.value for k in kinds}


def test_loan_aggregates_cd_and_1008(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    assert borrower.loan is not None
    # loan_id should be MultiSourced with CD primary + 1008 alternate
    assert borrower.loan.loan_id is not None
    loan_ids = [borrower.loan.loan_id.primary.value] + [
        a.value for a in borrower.loan.loan_id.alternates
    ]
    assert "TEST250700110" in loan_ids
    assert "TEST250700114" in loan_ids


def test_three_distinct_property_addresses(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    borrower, _ = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    cities = {p.address.value.city for p in borrower.properties}
    assert {"Washington", "Brentwood", "Citrus Springs"}.issubset(cities)


def test_output_json_loads_into_typescript_compatible_shape(
    fake_provider_loan_214: FakeProvider,
    loan_214_corpus: Path,
    tmp_path: Path,
) -> None:
    """Sanity-check the JSON shape the Next.js app reads."""
    folder = loan_214_corpus / "Loan Documents" / "Loan 214"
    _, output_path = run_borrower(folder, fake_provider_loan_214, output_dir=tmp_path)

    data = json.loads(output_path.read_text())
    # Top-level keys the UI relies on
    for key in (
        "id",
        "pii",
        "identifiers",
        "income",
        "accounts",
        "loan",
        "properties",
        "source_documents",
        "flags",
        "extraction_meta",
    ):
        assert key in data, f"missing {key}"
    # Nested provenance shape
    name_primary = data["pii"]["legal_name"]["primary"]
    assert {"value", "provenance"} <= name_primary.keys()
    assert {"document_id", "page", "confidence"} <= name_primary["provenance"].keys()
