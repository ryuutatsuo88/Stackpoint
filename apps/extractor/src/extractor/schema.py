"""Canonical data model for the loan-document extraction system.

Mirrors `docs/schema.md`. Treat this file as the source of truth for code;
treat `docs/schema.md` as the source of truth for humans. They must agree.

Design decisions:

- **Provenance everywhere.** Every extracted scalar that originates in a
  document carries a `Provenance` so the UI can render the source PDF beside
  the value. The UI promise is "every fact is traceable."
- **No premature reconciliation.** When the same logical fact appears in
  multiple documents (e.g. legal name on the W-2, paystub, and 1040), the
  aggregator stores all observed values with provenance and picks a primary
  per documented preference rules. Conflicts surface as `ExtractionFlag`s.
- **Forward-compatible extraction.** Extractors return strict-typed
  `*Fields` models for known doc types; unknown doc types and novel fields
  flow through the same `ExtractionFlag` channel rather than a parallel
  pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class Provenance(BaseModel):
    """Where a value came from, so the UI can highlight it on the source PDF."""

    document_id: str
    page: int = Field(..., ge=1, description="1-indexed page number")
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_text_excerpt: str | None = Field(
        None,
        description="Optional verbatim snippet showing where the value was read from.",
        max_length=500,
    )


class Sourced[T](BaseModel):
    """A value plus its provenance. Generic so the schema reads naturally.

    Pydantic v2 supports PEP 695 generics. We use this whenever we want to
    keep a single (value, provenance) pair. For multi-source facts, see
    `MultiSourced`.
    """

    model_config = ConfigDict(frozen=True)

    value: T
    provenance: Provenance


class MultiSourced[T](BaseModel):
    """A field with one chosen primary value and any number of alternates.

    Used when the same fact appears across multiple documents. The aggregator
    picks `primary` per the rules in `docs/schema.md`; `alternates` keeps the
    full audit trail. Conflicts also emit an `ExtractionFlag`.
    """

    primary: Sourced[T]
    alternates: list[Sourced[T]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Document descriptors
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    PAYSTUB = "paystub"
    W2 = "w2"
    EVOE = "evoe"
    FORM_1040 = "form_1040"
    SCHEDULE_1 = "schedule_1"
    SCHEDULE_C = "schedule_c"
    BANK_STATEMENT_CHECKING = "bank_statement_checking"
    BANK_STATEMENT_SAVINGS = "bank_statement_savings"
    CLOSING_DISCLOSURE = "closing_disclosure"
    TITLE_REPORT = "title_report"
    LETTER_OF_EXPLANATION = "letter_of_explanation"
    UNDERWRITING_TRANSMITTAL_1008 = "underwriting_transmittal_1008"
    UNKNOWN = "unknown"


class Document(BaseModel):
    """A single source PDF in the corpus."""

    id: str = Field(..., description="Stable ID derived from the file path / hash.")
    path: str = Field(..., description="Path relative to the corpus root.")
    filename: str
    page_count: int = Field(..., ge=1)
    sha256: str
    doc_type: DocumentType
    classifier_confidence: float = Field(..., ge=0.0, le=1.0)
    extracted_at: datetime
    bytes: int


# ---------------------------------------------------------------------------
# Person / borrower model
# ---------------------------------------------------------------------------


class Address(BaseModel):
    line_1: str
    line_2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str = "US"


class Contact(BaseModel):
    phone: str | None = None
    email: str | None = None


class PII(BaseModel):
    """Canonical identity for a borrower, with provenance per field."""

    legal_name: MultiSourced[str]
    date_of_birth: MultiSourced[date] | None = None
    address: MultiSourced[Address]
    contact: Contact = Field(default_factory=Contact)


class BorrowerIdentifiers(BaseModel):
    """Identifying numbers and alias names observed across the corpus."""

    ssn: MultiSourced[str] | None = None
    """SSN in canonical form `999-99-9999`. May be a masked variant if no
    full SSN was observed; if multiple distinct full SSNs are observed,
    that's a conflict flag, not a new alternate."""

    aliases: list[Sourced[str]] = Field(
        default_factory=list,
        description="Alternative spellings or partial-name variants observed.",
    )


# ---------------------------------------------------------------------------
# Employment / income
# ---------------------------------------------------------------------------


class EmploymentRecord(BaseModel):
    employer_name: Sourced[str]
    employer_address: Sourced[Address] | None = None
    job_title: Sourced[str] | None = None
    employment_status: Sourced[str] | None = None
    most_recent_start_date: Sourced[date] | None = None
    original_hire_date: Sourced[date] | None = None
    end_date: Sourced[date] | None = None
    pay_frequency: Sourced[str] | None = None
    rate_of_pay: Sourced[float] | None = None
    rate_basis: Sourced[Literal["hourly", "annual", "monthly", "other"]] | None = None


class IncomeKind(str, Enum):
    W2_WAGES = "w2_wages"
    W2_BOX1 = "w2_box1"  # taxable wages — separate so reconciliation stays explicit
    SOCIAL_SECURITY_WAGES = "social_security_wages"
    SELF_EMPLOYMENT_NET = "self_employment_net"
    SELF_EMPLOYMENT_GROSS = "self_employment_gross"
    OVERTIME = "overtime"
    COMMISSION = "commission"
    BONUS = "bonus"
    OTHER = "other"
    INTEREST = "interest"
    DIVIDENDS = "dividends"
    RENTAL = "rental"
    SOCIAL_SECURITY_BENEFIT = "social_security_benefit"
    PENSION = "pension"


class IncomeRecord(BaseModel):
    """A single income figure tied to a period and a source document.

    The aggregator emits one record per (kind, period, source_doc) tuple
    rather than reconciling across documents. The UI groups them.
    """

    kind: IncomeKind
    amount: Sourced[float]
    period_start: date | None = None
    period_end: date | None = None
    period_label: str | None = Field(
        None,
        description="Free-text label like '2024 annual', 'Pay 6/15-6/29', 'YTD 2025'.",
    )
    employer_name: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Accounts / loan / property
# ---------------------------------------------------------------------------


class AccountKind(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    OTHER = "other"


class Account(BaseModel):
    institution_name: Sourced[str]
    kind: AccountKind
    account_number: Sourced[str] = Field(
        ...,
        description="Stored as observed (masked or unmasked). Normalize at display time.",
    )
    holders: list[str] = Field(default_factory=list)
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    beginning_balance: Sourced[float] | None = None
    ending_balance: Sourced[float] | None = None
    interest_rate: Sourced[float] | None = None
    apy: Sourced[float] | None = None


class LoanTerm(BaseModel):
    description: str
    amount: float | None = None
    can_increase_after_closing: bool | None = None


class Loan(BaseModel):
    loan_id: MultiSourced[str] | None = None
    """Loan identifier(s) — may differ across docs; that's a conflict, not
    multiple loans."""

    purpose: Sourced[str] | None = None
    loan_type: Sourced[str] | None = None
    amortization_type: Sourced[str] | None = None
    loan_amount: MultiSourced[float] | None = None
    note_rate: Sourced[float] | None = None
    loan_term_months: Sourced[int] | None = None
    lender_name: Sourced[str] | None = None
    settlement_agent: Sourced[str] | None = None
    closing_date: Sourced[date] | None = None
    disbursement_date: Sourced[date] | None = None
    sale_price: Sourced[float] | None = None
    appraised_value: Sourced[float] | None = None
    ltv: Sourced[float] | None = None
    loan_terms: list[Sourced[LoanTerm]] = Field(default_factory=list)
    co_borrowers: list[str] = Field(default_factory=list)


class Property(BaseModel):
    role: Literal["subject", "other"]
    address: Sourced[Address]
    legal_description: Sourced[str] | None = None
    parcel_id: Sourced[str] | None = None
    occupancy_status: Sourced[str] | None = None


# ---------------------------------------------------------------------------
# Flags — the cross-doc + novelty surface
# ---------------------------------------------------------------------------


class FlagKind(str, Enum):
    NOVEL_FIELD = "novel_field"
    NOVEL_DOC_TYPE = "novel_doc_type"
    CONFLICT = "conflict"
    LOW_CONFIDENCE = "low_confidence"
    PARSING_ANOMALY = "parsing_anomaly"


class FlagSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class FlagStatus(str, Enum):
    OPEN = "open"
    ACK = "ack"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ExtractionFlag(BaseModel):
    """Anything a human should look at — novel fields, novel doc types,
    cross-doc conflicts, low-confidence extractions, parsing anomalies."""

    id: str
    kind: FlagKind
    severity: FlagSeverity
    summary: str
    """One-line human-readable description, for list views."""

    details: dict[str, Any] = Field(default_factory=dict)
    """Kind-specific structured payload. See the FlagKind docs for the shape
    of each variant."""

    documents: list[str] = Field(
        default_factory=list,
        description="document_ids involved in the flag",
    )
    field_path: str | None = Field(
        None,
        description="Dot-path into the Borrower model, e.g. 'pii.legal_name'.",
    )
    detected_at: datetime
    status: FlagStatus = FlagStatus.OPEN


# ---------------------------------------------------------------------------
# Top-level borrower record
# ---------------------------------------------------------------------------


class ExtractionMeta(BaseModel):
    extracted_at: datetime
    extractor_version: str
    llm_provider: str
    llm_model: str
    corpus_path: str
    duration_seconds: float


class Borrower(BaseModel):
    """The deliverable. One per loan folder under `documents/`."""

    id: str
    """Folder-derived ID, e.g. 'loan-214'."""

    pii: PII
    identifiers: BorrowerIdentifiers
    co_borrowers: list[PII] = Field(default_factory=list)
    """Additional people on the loan — e.g. a spouse with their own PII block."""

    employment: list[EmploymentRecord] = Field(default_factory=list)
    income: list[IncomeRecord] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    loan: Loan | None = None
    properties: list[Property] = Field(default_factory=list)

    source_documents: list[Document] = Field(default_factory=list)
    flags: list[ExtractionFlag] = Field(default_factory=list)
    extraction_meta: ExtractionMeta


# ---------------------------------------------------------------------------
# Per-doc-type "raw fields" payloads
# ---------------------------------------------------------------------------
# These mirror the docs/schema.md field inventories. They're the strict-typed
# return values from the per-doc extractors. The aggregator translates them
# into the higher-level Borrower record above.
# ---------------------------------------------------------------------------


class PaystubFields(BaseModel):
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
    federal_income_tax_current: float | None = None
    federal_income_tax_ytd: float | None = None
    state_tax_current: float | None = None
    state_tax_ytd: float | None = None
    social_security_current: float | None = None
    medicare_current: float | None = None
    earnings: list[dict[str, Any]] = Field(default_factory=list)
    other_benefits: list[dict[str, Any]] = Field(default_factory=list)
    deductions_other: list[dict[str, Any]] = Field(default_factory=list)
    direct_deposit: list[dict[str, Any]] = Field(default_factory=list)


class W2Fields(BaseModel):
    tax_year: int
    employer_ein: str | None = None
    employer_name: str
    employer_address: Address | None = None
    employee_ssn: str | None = None
    employee_name: str
    employee_address: Address | None = None
    box_1_wages: float
    box_2_federal_withheld: float | None = None
    box_3_ss_wages: float | None = None
    box_4_ss_withheld: float | None = None
    box_5_medicare_wages: float | None = None
    box_6_medicare_withheld: float | None = None
    box_12: list[dict[str, Any]] = Field(default_factory=list)
    box_13_retirement_plan: bool | None = None
    state_wages: float | None = None
    state_income_tax: float | None = None


class EvoeAnnualIncome(BaseModel):
    year: int
    base_salary: float | None = None
    overtime: float | None = None
    commissions: float | None = None
    bonus: float | None = None
    other: float | None = None
    total: float | None = None
    is_year_to_date: bool = False


class EvoeFields(BaseModel):
    subject_name: str
    subject_ssn_masked: str | None = None
    current_as_of_date: date | None = None
    employer_name: str
    employer_address: Address | None = None
    employment_status: str | None = None
    job_title: str | None = None
    most_recent_start_date: date | None = None
    original_hire_date: date | None = None
    end_date: date | None = None
    rate_of_pay: float | None = None
    pay_frequency: str | None = None
    pay_period_frequency: str | None = None
    annual_income: list[EvoeAnnualIncome] = Field(default_factory=list)


class Form1040Fields(BaseModel):
    tax_year: int
    filing_status: str | None = None
    taxpayer_name: str
    taxpayer_ssn: str | None = None
    spouse_name: str | None = None
    spouse_ssn: str | None = None
    address: Address | None = None
    dependents: list[dict[str, Any]] = Field(default_factory=list)
    line_1a_w2_wages: float | None = None
    line_1z_total_wages: float | None = None
    line_2b_taxable_interest: float | None = None
    line_3b_ordinary_dividends: float | None = None
    line_8_additional_income_sch1: float | None = None
    line_9_total_income: float | None = None
    line_11_agi: float | None = None
    line_12_deduction: float | None = None
    line_15_taxable_income: float | None = None
    line_24_total_tax: float | None = None
    line_33_total_payments: float | None = None
    line_34_overpayment: float | None = None
    line_37_amount_owed: float | None = None


class ScheduleCFields(BaseModel):
    tax_year: int
    proprietor_name: str
    proprietor_ssn: str | None = None
    business_name: str | None = None
    ein: str | None = None
    naics_code: str | None = None
    business_address: Address | None = None
    accounting_method: str | None = None
    line_1_gross_receipts: float | None = None
    line_7_gross_income: float | None = None
    line_28_total_expenses: float | None = None
    line_29_tentative_profit: float | None = None
    line_30_business_use_of_home: float | None = None
    line_31_net_profit: float


class BankTransaction(BaseModel):
    trans_date: date | None = None
    post_date: date | None = None
    description: str
    amount: float
    balance: float | None = None


class BankStatementFields(BaseModel):
    institution_name: str
    institution_address: Address | None = None
    account_holders: list[str] = Field(default_factory=list)
    holder_address: Address | None = None
    account_number: str
    product_name: str | None = None
    statement_period_start: date
    statement_period_end: date
    beginning_balance: float
    ending_balance: float
    total_credits: float | None = None
    total_debits: float | None = None
    interest_paid: float | None = None
    apy: float | None = None
    interest_rate: float | None = None
    transactions: list[BankTransaction] = Field(default_factory=list)


class ClosingDisclosureFields(BaseModel):
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
    loan_id: str | None = None
    loan_term: str | None = None
    loan_purpose: str | None = None
    loan_type: str | None = None
    product: str | None = None
    loan_terms: list[LoanTerm] = Field(default_factory=list)
    estimated_closing_costs: float | None = None
    estimated_cash_to_close: float | None = None


class TitleReportFields(BaseModel):
    issuing_agent: str | None = None
    commitment_number: str | None = None
    file_number: str | None = None
    loan_id_number: str | None = None
    property_address: Address | None = None
    legal_description: str | None = None
    county: str | None = None
    state: str | None = None
    parcel_id: str | None = None
    proposed_insureds: list[str] = Field(default_factory=list)
    proposed_amount_owner: float | None = None
    proposed_amount_loan: float | None = None
    current_vesting: str | None = None


class LetterOfExplanationFields(BaseModel):
    letter_date: date | None = None
    subject_topic: str | None = None
    referenced_event_date: date | None = None
    explanation_body: str
    signer_name: str | None = None
    signer_address: Address | None = None
    signer_phone: str | None = None
    signer_email: str | None = None


class Form1008Fields(BaseModel):
    """Fannie Form 1008 / Freddie Form 1077 — Uniform Underwriting Transmittal."""

    borrower_name: str
    co_borrower_name: str | None = None
    co_borrower_ssn: str | None = None
    total_borrowers: int | None = None
    property_address: Address | None = None
    occupancy_status: str | None = None
    sales_price: float | None = None
    appraised_value: float | None = None
    loan_type: str | None = None
    amortization_type: str | None = None
    loan_purpose: str | None = None
    lien_position: str | None = None
    loan_amount: float | None = None
    note_rate: float | None = None
    loan_term_months: int | None = None
    stable_monthly_income_total: float | None = None
    ltv: float | None = None
    cltv: float | None = None
    hcltv: float | None = None
    seller_loan_number: str | None = None
    self_employed_flag: bool | None = None


# A discriminated union so per-doc extractors can return strict types and the
# aggregator can switch on `doc_type` without isinstance chains.
KnownFields = (
    PaystubFields
    | W2Fields
    | EvoeFields
    | Form1040Fields
    | ScheduleCFields
    | BankStatementFields
    | ClosingDisclosureFields
    | TitleReportFields
    | LetterOfExplanationFields
    | Form1008Fields
)


# ---------------------------------------------------------------------------
# JSON Schema export
# ---------------------------------------------------------------------------


def borrower_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for `Borrower`. Consumed by the web app via a
    build step that emits `apps/web/lib/types.ts`.
    """
    return Borrower.model_json_schema()
