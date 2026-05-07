"""Per-doc-type extractors as a registry, with multi-pass support.

The Anthropic structured-output API has a hard limit on schema complexity:
no more than 16 nullable / union-typed parameters per output schema. Some
of our `*Fields` models exceed this (Form 1040, Form 1008, paystub,
bank statement). Rather than trim those — which would lose data — we
**split a single doc's extraction into multiple smaller LLM calls**, each
focused on a section of the doc with its own subset schema. The dicts are
merged and validated against the canonical `*Fields` model.

This is also more accurate: each call's prompt can be specific to the
section it cares about. The cost is N calls per doc instead of 1, but
Haiku is fast and cheap enough that this is preferable to data loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from extractor.llm.base import LLMProvider, LLMResponse, LLMUsage
from extractor.schema import (
    Address,
    BankStatementFields,
    BankTransaction,
    ClosingDisclosureFields,
    DocumentType,
    EvoeAnnualIncome,
    EvoeFields,
    Form1008Fields,
    Form1040Fields,
    LetterOfExplanationFields,
    LoanTerm,
    PaystubFields,
    ScheduleCFields,
    TitleReportFields,
    W2Fields,
)


_SHARED_SYSTEM = (
    "You are a precise extraction system for residential mortgage documents. "
    "Read the attached PDF and populate the requested schema. Use only "
    "values that appear in the document — never infer or fabricate. If a "
    "field isn't present, omit it (let the schema use its default). "
    "Dates must be parseable; normalize to YYYY-MM-DD. Numbers must be "
    "numeric (no $ or commas)."
)


# ---------------------------------------------------------------------------
# Shard sub-schemas for the dense doc types
# ---------------------------------------------------------------------------


# Form 1040 — split into PII / income / tax+refund
class _Form1040PII(BaseModel):
    tax_year: int
    filing_status: str | None = None
    taxpayer_name: str
    taxpayer_ssn: str | None = None
    spouse_name: str | None = None
    spouse_ssn: str | None = None
    address: Address | None = None
    # `dependents` deliberately omitted from this shard: list[dict[str, Any]]
    # produces an empty value-schema that Anthropic rejects, and the
    # aggregator doesn't consume it. The canonical Form1040Fields keeps it.


class _Form1040Income(BaseModel):
    line_1a_w2_wages: float | None = None
    line_1z_total_wages: float | None = None
    line_2b_taxable_interest: float | None = None
    line_3b_ordinary_dividends: float | None = None
    line_8_additional_income_sch1: float | None = None
    line_9_total_income: float | None = None


class _Form1040TaxRefund(BaseModel):
    line_11_agi: float | None = None
    line_12_deduction: float | None = None
    line_15_taxable_income: float | None = None
    line_24_total_tax: float | None = None
    line_33_total_payments: float | None = None
    line_34_overpayment: float | None = None
    line_37_amount_owed: float | None = None


# Paystub — split into header / deductions.
# The earnings / other_benefits / direct_deposit lists from the canonical
# PaystubFields are intentionally not in any shard: they're list[dict[str, Any]]
# which Anthropic rejects (empty value schema), and the aggregator doesn't
# consume them. They remain on the canonical model with empty defaults.
class _PaystubHeader(BaseModel):
    employer_name: str
    employer_address: Address | None = None
    employee_name: str
    employee_address: Address | None = None
    period_begin_date: date
    period_end_date: date
    pay_date: date
    basis_of_pay: str | None = None
    gross_pay_current: float
    gross_pay_ytd: float
    net_pay_current: float


class _PaystubDeductions(BaseModel):
    federal_income_tax_current: float | None = None
    federal_income_tax_ytd: float | None = None
    state_tax_current: float | None = None
    state_tax_ytd: float | None = None
    social_security_current: float | None = None
    medicare_current: float | None = None


# W-2 — split defensively (identity / wage boxes)
class _W2Identity(BaseModel):
    tax_year: int
    employer_name: str
    employer_address: Address | None = None
    employer_ein: str | None = None
    employee_name: str
    employee_ssn: str | None = None
    employee_address: Address | None = None


class _W2WageBoxes(BaseModel):
    box_1_wages: float
    box_2_federal_withheld: float | None = None
    box_3_ss_wages: float | None = None
    box_4_ss_withheld: float | None = None
    box_5_medicare_wages: float | None = None
    box_6_medicare_withheld: float | None = None
    state_wages: float | None = None
    state_income_tax: float | None = None


# EVOE — split into identity / employment / income
class _EvoeIdentity(BaseModel):
    subject_name: str
    subject_ssn_masked: str | None = None
    current_as_of_date: date | None = None


class _EvoeEmployment(BaseModel):
    employer_name: str
    employer_address: Address | None = None
    employment_status: str | None = None
    job_title: str | None = None
    most_recent_start_date: date | None = None
    original_hire_date: date | None = None
    end_date: date | None = None


class _EvoeIncomeShard(BaseModel):
    rate_of_pay: float | None = None
    pay_frequency: str | None = None
    pay_period_frequency: str | None = None
    annual_income: list[EvoeAnnualIncome] = Field(default_factory=list)


# Schedule C — split into identity / financials
class _ScheduleCIdentity(BaseModel):
    tax_year: int
    proprietor_name: str
    proprietor_ssn: str | None = None
    business_name: str | None = None
    ein: str | None = None
    naics_code: str | None = None
    business_address: Address | None = None
    accounting_method: str | None = None


class _ScheduleCFinancials(BaseModel):
    line_1_gross_receipts: float | None = None
    line_7_gross_income: float | None = None
    line_28_total_expenses: float | None = None
    line_29_tentative_profit: float | None = None
    line_30_business_use_of_home: float | None = None
    line_31_net_profit: float


# Closing Disclosure — split into closing/parties / loan info
class _CDClosingParties(BaseModel):
    date_issued: date | None = None
    closing_date: date | None = None
    disbursement_date: date | None = None
    settlement_agent: str | None = None
    file_number: str | None = None
    property_address: Address | None = None
    sale_price: float | None = None
    borrower_names: list[str] = Field(default_factory=list)
    seller_name: str | None = None
    lender_name: str | None = None


class _CDLoanInfo(BaseModel):
    loan_id: str | None = None
    loan_term: str | None = None
    loan_purpose: str | None = None
    loan_type: str | None = None
    product: str | None = None
    estimated_closing_costs: float | None = None
    estimated_cash_to_close: float | None = None


class _CDLoanTerms(BaseModel):
    """LoanTerm itself has nullable fields; isolate it in its own shard."""

    loan_terms: list[LoanTerm] = Field(default_factory=list)


# Title Report — split into identification / property+policies
class _TitleRptIdent(BaseModel):
    issuing_agent: str | None = None
    commitment_number: str | None = None
    file_number: str | None = None
    loan_id_number: str | None = None


class _TitleRptProperty(BaseModel):
    property_address: Address | None = None
    legal_description: str | None = None
    county: str | None = None
    state: str | None = None
    parcel_id: str | None = None
    proposed_insureds: list[str] = Field(default_factory=list)
    proposed_amount_owner: float | None = None
    proposed_amount_loan: float | None = None
    current_vesting: str | None = None


# Form 1008 — split into borrower/property / loan terms / underwriting
class _Form1008BorrowerProperty(BaseModel):
    borrower_name: str
    co_borrower_name: str | None = None
    co_borrower_ssn: str | None = None
    total_borrowers: int | None = None
    property_address: Address | None = None
    occupancy_status: str | None = None
    sales_price: float | None = None
    appraised_value: float | None = None


class _Form1008Loan(BaseModel):
    loan_type: str | None = None
    amortization_type: str | None = None
    loan_purpose: str | None = None
    lien_position: str | None = None
    loan_amount: float | None = None
    note_rate: float | None = None
    loan_term_months: int | None = None
    seller_loan_number: str | None = None


class _Form1008Underwriting(BaseModel):
    stable_monthly_income_total: float | None = None
    ltv: float | None = None
    cltv: float | None = None
    hcltv: float | None = None
    self_employed_flag: bool | None = None


# Bank statement — split into header / balances / transactions
class _BankStatementHeader(BaseModel):
    institution_name: str
    institution_address: Address | None = None
    account_holders: list[str] = Field(default_factory=list)
    holder_address: Address | None = None
    account_number: str
    product_name: str | None = None
    statement_period_start: date
    statement_period_end: date


class _BankStatementBalances(BaseModel):
    beginning_balance: float
    ending_balance: float
    total_credits: float | None = None
    total_debits: float | None = None
    interest_paid: float | None = None
    apy: float | None = None
    interest_rate: float | None = None


class _BankStatementTransactions(BaseModel):
    transactions: list[BankTransaction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Shard:
    schema: type[BaseModel]
    instructions: str
    """What this shard should focus on within the document."""


@dataclass(frozen=True)
class _Extractor:
    final_schema: type[BaseModel]
    shards: list[_Shard]
    """One or more LLM calls. If a single doc-type's full schema fits
    inside Anthropic's 16-union limit, this is one shard equal to the
    final schema. Dense doc types use multiple sub-schemas merged at
    the end."""


REGISTRY: dict[DocumentType, _Extractor] = {
    DocumentType.W2: _Extractor(
        final_schema=W2Fields,
        shards=[
            _Shard(
                schema=_W2Identity,
                instructions=(
                    "Extract the W-2 identity block: tax year, employer "
                    "(name/address/EIN), employee (name/SSN/address)."
                ),
            ),
            _Shard(
                schema=_W2WageBoxes,
                instructions=(
                    "Extract the W-2 wage boxes (1, 2, 3, 4, 5, 6, plus state "
                    "wages and state income tax). Use the box numbers as the "
                    "source of truth — form layout is unreliable."
                ),
            ),
        ],
    ),
    DocumentType.EVOE: _Extractor(
        final_schema=EvoeFields,
        shards=[
            _Shard(
                schema=_EvoeIdentity,
                instructions=(
                    "Extract the EVOE subject identity (subject_name, masked "
                    "SSN, current_as_of_date)."
                ),
            ),
            _Shard(
                schema=_EvoeEmployment,
                instructions=(
                    "Extract the EVOE employment block: employer, "
                    "employment_status, job_title, hire/start/end dates."
                ),
            ),
            _Shard(
                schema=_EvoeIncomeShard,
                instructions=(
                    "Extract the EVOE income block: rate_of_pay, "
                    "pay_frequency, pay_period_frequency, and the annual "
                    "income table. Mark is_year_to_date=true for partial-"
                    "year rows."
                ),
            ),
        ],
    ),
    DocumentType.SCHEDULE_C: _Extractor(
        final_schema=ScheduleCFields,
        shards=[
            _Shard(
                schema=_ScheduleCIdentity,
                instructions=(
                    "Extract Schedule C identity (tax_year, proprietor name "
                    "and SSN, business name, EIN, NAICS, address, "
                    "accounting method). **If multiple tax years are "
                    "stacked, return the MOST RECENT only.**"
                ),
            ),
            _Shard(
                schema=_ScheduleCFinancials,
                instructions=(
                    "Extract Schedule C financials: line 1, 7, 28, 29, 30, "
                    "and 31 (net profit — required). **Most recent year only.**"
                ),
            ),
        ],
    ),
    DocumentType.CLOSING_DISCLOSURE: _Extractor(
        final_schema=ClosingDisclosureFields,
        shards=[
            _Shard(
                schema=_CDClosingParties,
                instructions=(
                    "Extract Closing Disclosure closing details and parties: "
                    "issue/closing/disbursement dates, settlement agent, "
                    "file number, property address, sale price, borrowers, "
                    "seller, lender."
                ),
            ),
            _Shard(
                schema=_CDLoanInfo,
                instructions=(
                    "Extract Closing Disclosure loan info: loan_id, "
                    "loan_term, purpose, type, product, estimated closing "
                    "costs, cash to close."
                ),
            ),
            _Shard(
                schema=_CDLoanTerms,
                instructions=(
                    "Extract the Closing Disclosure's `loan_terms` table — "
                    "loan amount, interest rate, monthly P&I, prepayment "
                    "penalty, balloon payment — each as "
                    "{description, amount, can_increase_after_closing}."
                ),
            ),
        ],
    ),
    DocumentType.TITLE_REPORT: _Extractor(
        final_schema=TitleReportFields,
        shards=[
            _Shard(
                schema=_TitleRptIdent,
                instructions=(
                    "Extract Title Commitment identification: issuing agent, "
                    "commitment number, file number, loan id."
                ),
            ),
            _Shard(
                schema=_TitleRptProperty,
                instructions=(
                    "Extract Title Commitment Schedule A and Exhibit A: "
                    "property address, legal description, county, state, "
                    "parcel id, proposed insureds, proposed insurance "
                    "amounts, current vesting."
                ),
            ),
        ],
    ),
    DocumentType.LETTER_OF_EXPLANATION: _Extractor(
        final_schema=LetterOfExplanationFields,
        shards=[
            _Shard(
                schema=LetterOfExplanationFields,
                instructions=(
                    "Extract the letter of explanation. `subject_topic` is a "
                    "label for what's being explained. "
                    "`referenced_event_date` is the event date, NOT the "
                    "letter's date."
                ),
            )
        ],
    ),
    DocumentType.PAYSTUB: _Extractor(
        final_schema=PaystubFields,
        shards=[
            _Shard(
                schema=_PaystubHeader,
                instructions=(
                    "Extract the paystub header: employer, employee, pay "
                    "period dates, gross/net pay totals."
                ),
            ),
            _Shard(
                schema=_PaystubDeductions,
                instructions=(
                    "Extract the paystub's statutory deductions (federal "
                    "income tax, state, SS, medicare) split current vs YTD."
                ),
            ),
        ],
    ),
    DocumentType.FORM_1040: _Extractor(
        final_schema=Form1040Fields,
        shards=[
            _Shard(
                schema=_Form1040PII,
                instructions=(
                    "Extract Form 1040 PII: tax year, filing status, "
                    "taxpayer/spouse names + SSNs, address, dependents. "
                    "**If multiple tax years are stacked, return the MOST "
                    "RECENT (highest tax_year) only.**"
                ),
            ),
            _Shard(
                schema=_Form1040Income,
                instructions=(
                    "Extract Form 1040 income lines (1a, 1z, 2b, 3b, 8, 9). "
                    "**If multiple tax years are stacked, use the MOST RECENT.**"
                ),
            ),
            _Shard(
                schema=_Form1040TaxRefund,
                instructions=(
                    "Extract Form 1040 tax/refund lines (11, 12, 15, 24, 33, "
                    "34, 37). **Most recent year only.**"
                ),
            ),
        ],
    ),
    DocumentType.UNDERWRITING_TRANSMITTAL_1008: _Extractor(
        final_schema=Form1008Fields,
        shards=[
            _Shard(
                schema=_Form1008BorrowerProperty,
                instructions=(
                    "Extract Form 1008 Section I (borrower & property): "
                    "names, SSNs, property address, occupancy, sales price, "
                    "appraised value."
                ),
            ),
            _Shard(
                schema=_Form1008Loan,
                instructions=(
                    "Extract Form 1008 Section II (mortgage): loan type, "
                    "amortization, purpose, lien position, amount, rate, "
                    "term, seller loan number."
                ),
            ),
            _Shard(
                schema=_Form1008Underwriting,
                instructions=(
                    "Extract Form 1008 Section III (underwriting): stable "
                    "monthly income total, LTV/CLTV/HCLTV ratios, "
                    "self-employed flag."
                ),
            ),
        ],
    ),
    DocumentType.BANK_STATEMENT_CHECKING: _Extractor(
        final_schema=BankStatementFields,
        shards=[
            _Shard(
                schema=_BankStatementHeader,
                instructions=(
                    "Extract the bank statement header: institution, account "
                    "holders + address, account number, product, statement "
                    "period."
                ),
            ),
            _Shard(
                schema=_BankStatementBalances,
                instructions=(
                    "Extract the bank statement's balance summary: beginning "
                    "and ending balance, total credits, total debits, "
                    "interest paid, APY, interest rate."
                ),
            ),
            _Shard(
                schema=_BankStatementTransactions,
                instructions=(
                    "Extract every transaction row from the statement. Join "
                    "multi-line descriptions. If there are no transactions, "
                    "return an empty list."
                ),
            ),
        ],
    ),
    DocumentType.BANK_STATEMENT_SAVINGS: _Extractor(
        final_schema=BankStatementFields,
        shards=[
            _Shard(
                schema=_BankStatementHeader,
                instructions=(
                    "Extract the savings statement header: institution, "
                    "holders, account number, product, statement period."
                ),
            ),
            _Shard(
                schema=_BankStatementBalances,
                instructions=(
                    "Extract the savings statement's balances: beginning, "
                    "ending, interest paid, APY, interest rate."
                ),
            ),
            _Shard(
                schema=_BankStatementTransactions,
                instructions=(
                    "Extract any transaction rows. Boilerplate disclosure "
                    "pages have none — return an empty list in that case."
                ),
            ),
        ],
    ),
}


def supported_doc_types() -> set[DocumentType]:
    return set(REGISTRY.keys())


def extract(
    doc_type: DocumentType,
    pdf_path: Path,
    provider: LLMProvider,
    *,
    with_novelty: bool = False,
) -> LLMResponse[Any]:
    """Run the registered extractor for `doc_type` on `pdf_path`.

    For doc types with multiple shards, runs each shard in sequence, merges
    the partial dicts, and validates against the canonical `final_schema`.
    `with_novelty=True` is ignored when there are multiple shards (the
    wrapper schema would compound the union-count problem).
    """
    if doc_type not in REGISTRY:
        raise ValueError(f"No extractor registered for {doc_type}")
    entry = REGISTRY[doc_type]

    # Single-shard fast path
    if len(entry.shards) == 1:
        shard = entry.shards[0]
        if with_novelty:
            return provider.extract_with_novelty(
                pdf_path,
                shard.schema,
                shard.instructions,
                system=_SHARED_SYSTEM,
            )
        return provider.extract_structured(
            pdf_path,
            shard.schema,
            shard.instructions,
            system=_SHARED_SYSTEM,
        )

    # Multi-shard: call each, merge, validate against final_schema.
    merged: dict[str, Any] = {}
    total_usage = LLMUsage()
    raw_shards: list[dict[str, Any]] = []

    for shard in entry.shards:
        response = provider.extract_structured(
            pdf_path,
            shard.schema,
            shard.instructions,
            system=_SHARED_SYSTEM,
        )
        partial = response.parsed.model_dump(mode="json", exclude_none=True)
        merged.update(partial)
        total_usage = LLMUsage(
            input_tokens=total_usage.input_tokens + response.usage.input_tokens,
            output_tokens=total_usage.output_tokens + response.usage.output_tokens,
            cache_read_tokens=total_usage.cache_read_tokens + response.usage.cache_read_tokens,
            cache_write_tokens=total_usage.cache_write_tokens + response.usage.cache_write_tokens,
        )
        raw_shards.append(response.raw)

    final = entry.final_schema.model_validate(merged)
    return LLMResponse(parsed=final, usage=total_usage, raw={"shards": raw_shards})
