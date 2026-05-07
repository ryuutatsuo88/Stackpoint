"""Shared pytest fixtures.

`fake_provider_loan_214` ships canned LLM responses for the entire Loan 214
corpus so the end-to-end pipeline test runs without the network. The
fixtures are realistic but synthetic — values from the corpus walk-through,
not the actual LLM output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from extractor.llm.fake import FakeProvider


@pytest.fixture
def fake_provider_loan_214() -> FakeProvider:
    structured: dict[tuple[str, str], dict[str, Any]] = {
        # Paystub
        (
            "Paystub- John Homeowner (Current).pdf",
            "PaystubFields",
        ): {
            "employer_name": "ABC Technologies",
            "employer_address": {
                "line_1": "1 Tech Plaza",
                "city": "Louisville",
                "state": "KY",
                "postal_code": "40207",
            },
            "employee_name": "John Homeowner",
            "employee_address": {
                "line_1": "175 13th Street",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "period_begin_date": "2025-06-01",
            "period_end_date": "2025-06-15",
            "pay_date": "2025-06-20",
            "basis_of_pay": "Salary",
            "gross_pay_current": 4961.54,
            "gross_pay_ytd": 64500.00,
            "net_pay_current": 3377.21,
            "federal_income_tax_current": 723.00,
            "federal_income_tax_ytd": 9399.00,
        },
        # W-2
        (
            "W2 2024- John Homeowner.pdf",
            "W2Fields",
        ): {
            "tax_year": 2024,
            "employer_ein": "11-2223334",
            "employer_name": "ABC Technologies",
            "employee_ssn": "999-40-5000",
            "employee_name": "John Homeowner",
            "employee_address": {
                "line_1": "175 13th Street",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "box_1_wages": 117040.19,
            "box_2_federal_withheld": 14980.17,
            "box_3_ss_wages": 121790.22,
            "box_4_ss_withheld": 7550.98,
            "box_5_medicare_wages": 121790.22,
            "box_6_medicare_withheld": 1765.96,
            "box_12": [
                {"code": "C", "amount": 5112.00},
                {"code": "D", "amount": 1800.00},
                {"code": "W", "amount": 22500.00},
            ],
            "box_13_retirement_plan": True,
        },
        # EVOE
        (
            "EVOE - John Homeowner.pdf",
            "EvoeFields",
        ): {
            "subject_name": "John Homeowner",
            "subject_ssn_masked": "xxx-xx-5000",
            "current_as_of_date": "2025-06-30",
            "employer_name": "ABC Technologies",
            "employer_address": {
                "line_1": "1 Tech Plaza",
                "city": "Louisville",
                "state": "KY",
                "postal_code": "40207",
            },
            "employment_status": "Active",
            "job_title": "Sales Manager",
            "most_recent_start_date": "2016-04-15",
            "rate_of_pay": 110000.00,
            "pay_frequency": "Annual",
            "pay_period_frequency": "Bi-Weekly",
            "annual_income": [
                {"year": 2025, "base_salary": 60000, "total": 65000, "is_year_to_date": True},
                {"year": 2024, "base_salary": 110000, "commissions": 11790.22, "total": 121790.22},
                {"year": 2023, "base_salary": 105000, "commissions": 8000, "total": 113000},
            ],
        },
        # 1040 (most recent year)
        (
            "1040 and Schedule C (2023 and 2024) - John and Mary Homeowner .pdf",
            "Form1040Fields",
        ): {
            "tax_year": 2024,
            "filing_status": "Married Filing Jointly",
            "taxpayer_name": "John Homeowner",
            "taxpayer_ssn": "999-40-5000",
            "spouse_name": "Mary Homeowner",
            "spouse_ssn": "500-22-2000",
            "address": {
                "line_1": "175 13th Street",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "line_1a_w2_wages": 143920.00,
            "line_1z_total_wages": 143920.00,
            "line_8_additional_income_sch1": 28341.00,
            "line_9_total_income": 172261.00,
            "line_11_agi": 170261.00,
            "line_12_deduction": 29200.00,
            "line_15_taxable_income": 141061.00,
        },
        # Checking
        (
            "Checking - John Mary Homeowner (Current).pdf",
            "BankStatementFields",
        ): {
            "institution_name": "Sandy Springs Credit Union",
            "account_holders": ["John Homeowner", "Mary Homeowner"],
            "holder_address": {
                "line_1": "175 13th Street",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "account_number": "123456789",
            "product_name": "EasyChecking",
            "statement_period_start": "2025-06-01",
            "statement_period_end": "2025-06-30",
            "beginning_balance": 12450.32,
            "ending_balance": 14820.91,
            "total_credits": 9871.50,
            "total_debits": 7500.91,
            "interest_paid": 0.00,
            "transactions": [],
        },
        # Savings
        (
            "Savings - John Mary Homeowner (Current).pdf",
            "BankStatementFields",
        ): {
            "institution_name": "Sandy Springs Credit Union",
            "account_holders": ["John Homeowner", "Mary Homeowner"],
            "account_number": "987654321",
            "product_name": "360 Savings",
            "statement_period_start": "2025-06-01",
            "statement_period_end": "2025-06-30",
            "beginning_balance": 45000.00,
            "ending_balance": 47228.18,
            "total_credits": 2228.18,
            "total_debits": 0.00,
            "interest_paid": 28.18,
            "apy": 0.753,
            "interest_rate": 0.750,
            "transactions": [],
        },
        # CD
        (
            "Closing_Disclosure.pdf",
            "ClosingDisclosureFields",
        ): {
            "date_issued": "2025-07-15",
            "closing_date": "2025-08-01",
            "disbursement_date": "2025-08-01",
            "settlement_agent": "ABC Title",
            "file_number": "123456789",
            "property_address": {
                "line_1": "999 Test Place",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "sale_price": 350000.00,
            "borrower_names": ["John Homeowner", "Mary Homeowner"],
            "lender_name": "XYZ Mortgage Company",
            "loan_id": "TEST250700110",
            "loan_term": "30 years",
            "loan_purpose": "Purchase",
            "loan_type": "Conventional",
            "product": "Fixed Rate",
            "loan_terms": [
                {"description": "Loan Amount", "amount": 280000.00},
                {"description": "Interest Rate", "amount": 6.5},
            ],
            "estimated_closing_costs": 12500.00,
            "estimated_cash_to_close": 82500.00,
        },
        # Form 1008
        (
            "document.pdf",
            "Form1008Fields",
        ): {
            "borrower_name": "John Homeowner",
            "co_borrower_name": "Mary Homeowner",
            "co_borrower_ssn": "500-60-2222",
            "total_borrowers": 2,
            "property_address": {
                "line_1": "214 Overlook Drive",
                "city": "Brentwood",
                "state": "TN",
                "postal_code": "37027",
            },
            "occupancy_status": "Primary Residence",
            "sales_price": 350000.00,
            "loan_type": "Conventional",
            "amortization_type": "Fixed Rate",
            "loan_purpose": "Purchase",
            "lien_position": "First Mortgage",
            "loan_amount": 280000.00,
            "ltv": 80.0,
            "cltv": 80.0,
            "hcltv": 80.0,
            "seller_loan_number": "TEST250700114",
        },
        # Title Report (different transaction!)
        (
            "Title Report.pdf",
            "TitleReportFields",
        ): {
            "issuing_agent": "Clear Choice Title, Inc.",
            "commitment_number": "25-080ME",
            "file_number": "25-080ME",
            "loan_id_number": "2504EM060965",
            "property_address": {
                "line_1": "9591 North Old Mill Way",
                "city": "Citrus Springs",
                "state": "FL",
                "postal_code": "34433",
            },
            "legal_description": "Lot 4, Block 308, Citrus Springs Unit 3",
            "county": "Citrus",
            "state": "FL",
            "parcel_id": "18E17S100030 03080 0040",
            "proposed_insureds": ["Robert VanAssen", "Andrea VanAssen"],
            "proposed_amount_owner": 258000.00,
            "proposed_amount_loan": 232200.00,
            "current_vesting": "Heirs/devisees of Linda Gay Brown",
        },
        # LOE
        (
            "Letter_of_Explanation.pdf",
            "LetterOfExplanationFields",
        ): {
            "letter_date": "2025-06-30",
            "subject_topic": "Recent credit inquiry",
            "referenced_event_date": "2024-06-15",
            "explanation_body": "The credit inquiry on 06/15/2024 was for an auto loan I did not ultimately pursue.",
            "signer_name": "John Homeowner",
            "signer_address": {
                "line_1": "175 13th Street",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20013",
            },
            "signer_phone": "347-324-1888",
            "signer_email": "john.homeowner@test.com",
        },
    }

    # Novelty is opt-in per pipeline call and only fires for single-shard
    # doc types (multi-shard schemas can't wrap in ExtractionWithNovelty
    # without busting the same union-count limit they were split to avoid).
    # Letter of Explanation stays single-shard.
    novelty: dict[tuple[str, str], list[dict[str, Any]]] = {
        ("Letter_of_Explanation.pdf", "LetterOfExplanationFields"): [
            {
                "field_name": "disclaimer_footer",
                "sample_value": "This document is provided for...",
                "suggested_type": "str",
                "notes": "boilerplate footer not in current schema",
            },
        ],
    }

    classifications: dict[str, tuple[str, float]] = {
        "Paystub- John Homeowner (Current).pdf": ("paystub", 0.99),
        "W2 2024- John Homeowner.pdf": ("w2", 0.99),
        "EVOE - John Homeowner.pdf": ("evoe", 0.99),
        "1040 and Schedule C (2023 and 2024) - John and Mary Homeowner .pdf": ("form_1040", 0.95),
        "Checking - John Mary Homeowner (Current).pdf": ("bank_statement_checking", 0.99),
        "Savings - John Mary Homeowner (Current).pdf": ("bank_statement_savings", 0.99),
        "Closing_Disclosure.pdf": ("closing_disclosure", 0.99),
        "Title Report.pdf": ("title_report", 0.99),
        "Letter_of_Explanation.pdf": ("letter_of_explanation", 0.99),
        "document.pdf": ("underwriting_transmittal_1008", 0.85),
    }

    return FakeProvider(
        structured=structured,
        novelty=novelty,
        classifications=classifications,
    )


@pytest.fixture
def loan_214_corpus(tmp_path: Path) -> Path:
    """A synthetic Loan 214 corpus on disk — empty PDFs with the right
    filenames so the pipeline can iterate them. The FakeProvider keys off
    the filename, so contents don't matter.
    """
    corpus = tmp_path / "documents"
    folder = corpus / "Loan Documents" / "Loan 214"
    folder.mkdir(parents=True)
    for filename in [
        "Paystub- John Homeowner (Current).pdf",
        "W2 2024- John Homeowner.pdf",
        "EVOE - John Homeowner.pdf",
        "1040 and Schedule C (2023 and 2024) - John and Mary Homeowner .pdf",
        "Checking - John Mary Homeowner (Current).pdf",
        "Savings - John Mary Homeowner (Current).pdf",
        "Closing_Disclosure.pdf",
        "Title Report.pdf",
        "Letter_of_Explanation.pdf",
        "document.pdf",
    ]:
        (folder / filename).write_bytes(b"%PDF-1.4 fake content")
    return corpus
