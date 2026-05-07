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
    # Single-shard (schema fits the limit)
    DocumentType.W2: _Extractor(
        final_schema=W2Fields,
        shards=[
            _Shard(
                schema=W2Fields,
                instructions=(
                    "Extract the W-2. Use box numbers as the source of truth "
                    "— form layout is unreliable. Box 12 is a list of "
                    "(code, amount) pairs."
                ),
            )
        ],
    ),
    DocumentType.EVOE: _Extractor(
        final_schema=EvoeFields,
        shards=[
            _Shard(
                schema=EvoeFields,
                instructions=(
                    "Extract the verification of employment. Mark "
                    "is_year_to_date=true for partial-year rows in "
                    "annual_income."
                ),
            )
        ],
    ),
    DocumentType.SCHEDULE_C: _Extractor(
        final_schema=ScheduleCFields,
        shards=[
            _Shard(
                schema=ScheduleCFields,
                instructions=(
                    "Extract Schedule C. **If multiple tax years are stacked, "
                    "extract the MOST RECENT only.** Net profit (line 31) is "
                    "the headline figure."
                ),
            )
        ],
    ),
    DocumentType.CLOSING_DISCLOSURE: _Extractor(
        final_schema=ClosingDisclosureFields,
        shards=[
            _Shard(
                schema=ClosingDisclosureFields,
                instructions=(
                    "Extract the closing disclosure. This corpus may contain "
                    "partial / non-CFPB-standard CDs — extract whatever is "
                    "present."
                ),
            )
        ],
    ),
    DocumentType.TITLE_REPORT: _Extractor(
        final_schema=TitleReportFields,
        shards=[
            _Shard(
                schema=TitleReportFields,
                instructions=(
                    "Extract from the ALTA Title Commitment. Schedule A holds "
                    "the core fields (insureds, property address, commitment "
                    "number, policies). Skip boilerplate."
                ),
            )
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
    # Multi-shard
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
