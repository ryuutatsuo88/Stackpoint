"""Per-doc extractions → single `Borrower` record.

The aggregator preserves *every* observed value with provenance. When the
same logical fact appears in N docs, primary is picked via the rules in
docs/schema.md and the others land in `alternates`. Conflicts between
primary and any alternate also emit a flag (see consistency.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from extractor.consistency import detect_conflicts
from extractor.llm.base import NovelFieldHint
from extractor.schema import (
    Account,
    AccountKind,
    Address,
    BankStatementFields,
    Borrower,
    BorrowerIdentifiers,
    ClosingDisclosureFields,
    Contact,
    Document,
    DocumentType,
    EmploymentRecord,
    EvoeFields,
    ExtractionFlag,
    ExtractionMeta,
    FlagKind,
    FlagSeverity,
    Form1008Fields,
    Form1040Fields,
    IncomeKind,
    IncomeRecord,
    Loan,
    LoanTerm,
    MultiSourced,
    PaystubFields,
    PII,
    Property,
    Provenance,
    ScheduleCFields,
    Sourced,
    TitleReportFields,
    W2Fields,
)


def aggregate(
    *,
    borrower_id: str,
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
    meta: ExtractionMeta,
) -> Borrower:
    """Merge per-doc field models into a single `Borrower`."""

    docs_by_id = {doc.id: doc for doc, _, _ in extractions}
    typed: list[tuple[str, DocumentType, Any]] = [
        (doc.id, doc.doc_type, fields) for doc, fields, _ in extractions
    ]

    pii = _build_pii(extractions)
    identifiers = _build_identifiers(extractions)
    employment = _build_employment(extractions)
    income = _build_income(extractions)
    accounts = _build_accounts(extractions)
    loan = _build_loan(extractions)
    properties = _build_properties(extractions)

    flags: list[ExtractionFlag] = list(detect_conflicts(typed))
    flags.extend(_novel_field_flags(extractions))
    flags.extend(_low_confidence_flags(docs_by_id))

    return Borrower(
        id=borrower_id,
        pii=pii,
        identifiers=identifiers,
        employment=employment,
        income=income,
        accounts=accounts,
        loan=loan,
        properties=properties,
        source_documents=[doc for doc, _, _ in extractions],
        flags=flags,
        extraction_meta=meta,
    )


# ---------------------------------------------------------------------------
# section builders
# ---------------------------------------------------------------------------


def _build_pii(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> PII:
    """Preference for legal name: 1040 → W-2 → EVOE → CD → bank stmt → paystub.
    Address: paystub (most recent) → W-2 → 1040 → bank stmt.
    """
    name_candidates: list[Sourced[str]] = []
    address_candidates: list[Sourced[Address]] = []
    contact = Contact()

    name_priority: dict[type, int] = {
        Form1040Fields: 0,
        W2Fields: 1,
        EvoeFields: 2,
        ClosingDisclosureFields: 3,
        BankStatementFields: 4,
        PaystubFields: 5,
    }
    addr_priority: dict[type, int] = {
        PaystubFields: 0,
        W2Fields: 1,
        Form1040Fields: 2,
        BankStatementFields: 3,
    }

    for doc, fields, _ in extractions:
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)

        if isinstance(fields, PaystubFields):
            name_candidates.append(Sourced[str](value=fields.employee_name, provenance=prov))
            if fields.employee_address:
                address_candidates.append(
                    Sourced[Address](value=fields.employee_address, provenance=prov)
                )
        elif isinstance(fields, W2Fields):
            name_candidates.append(Sourced[str](value=fields.employee_name, provenance=prov))
            if fields.employee_address:
                address_candidates.append(
                    Sourced[Address](value=fields.employee_address, provenance=prov)
                )
        elif isinstance(fields, EvoeFields):
            name_candidates.append(Sourced[str](value=fields.subject_name, provenance=prov))
        elif isinstance(fields, Form1040Fields):
            name_candidates.append(Sourced[str](value=fields.taxpayer_name, provenance=prov))
            if fields.address:
                address_candidates.append(Sourced[Address](value=fields.address, provenance=prov))
        elif isinstance(fields, BankStatementFields):
            if fields.account_holders:
                name_candidates.append(
                    Sourced[str](value=fields.account_holders[0], provenance=prov)
                )
            if fields.holder_address:
                address_candidates.append(
                    Sourced[Address](value=fields.holder_address, provenance=prov)
                )
        elif isinstance(fields, LetterOfExplanationFields := type(fields)):  # noqa: F841 — using class shadow for narrow type check
            from extractor.schema import LetterOfExplanationFields as _LOE
            if isinstance(fields, _LOE):
                if fields.signer_phone:
                    contact = Contact(phone=fields.signer_phone, email=fields.signer_email)

    name_candidates.sort(
        key=lambda s: name_priority.get(_origin_type(s, extractions), 99)
    )
    address_candidates.sort(
        key=lambda s: addr_priority.get(_origin_type(s, extractions), 99)
    )

    if not name_candidates:
        raise ValueError("No name candidates found across the corpus.")
    if not address_candidates:
        raise ValueError("No address candidates found across the corpus.")

    return PII(
        legal_name=MultiSourced[str](
            primary=name_candidates[0],
            alternates=name_candidates[1:],
        ),
        address=MultiSourced[Address](
            primary=address_candidates[0],
            alternates=address_candidates[1:],
        ),
        contact=contact,
    )


def _origin_type(
    sourced: Sourced[Any],
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> type:
    for doc, fields, _ in extractions:
        if doc.id == sourced.provenance.document_id:
            return type(fields)
    return type(None)


def _build_identifiers(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> BorrowerIdentifiers:
    ssn_candidates: list[Sourced[str]] = []
    for doc, fields, _ in extractions:
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)
        ssn: str | None = None
        if isinstance(fields, Form1040Fields):
            ssn = fields.taxpayer_ssn
        elif isinstance(fields, W2Fields):
            ssn = fields.employee_ssn
        elif isinstance(fields, EvoeFields):
            ssn = fields.subject_ssn_masked
        if ssn:
            ssn_candidates.append(Sourced[str](value=ssn, provenance=prov))

    ssn_field = None
    if ssn_candidates:
        full_ssns = [s for s in ssn_candidates if "x" not in s.value.lower() and "*" not in s.value]
        ordered = full_ssns + [s for s in ssn_candidates if s not in full_ssns]
        ssn_field = MultiSourced[str](primary=ordered[0], alternates=ordered[1:])

    return BorrowerIdentifiers(ssn=ssn_field)


def _build_employment(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> list[EmploymentRecord]:
    out: list[EmploymentRecord] = []
    for doc, fields, _ in extractions:
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)
        if isinstance(fields, EvoeFields):
            out.append(
                EmploymentRecord(
                    employer_name=Sourced[str](value=fields.employer_name, provenance=prov),
                    employer_address=(
                        Sourced[Address](value=fields.employer_address, provenance=prov)
                        if fields.employer_address
                        else None
                    ),
                    job_title=(
                        Sourced[str](value=fields.job_title, provenance=prov)
                        if fields.job_title
                        else None
                    ),
                    employment_status=(
                        Sourced[str](value=fields.employment_status, provenance=prov)
                        if fields.employment_status
                        else None
                    ),
                    most_recent_start_date=(
                        Sourced[Any](value=fields.most_recent_start_date, provenance=prov)
                        if fields.most_recent_start_date
                        else None
                    ),
                    pay_frequency=(
                        Sourced[str](value=fields.pay_frequency, provenance=prov)
                        if fields.pay_frequency
                        else None
                    ),
                    rate_of_pay=(
                        Sourced[float](value=fields.rate_of_pay, provenance=prov)
                        if fields.rate_of_pay is not None
                        else None
                    ),
                )
            )
    return out


def _build_income(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> list[IncomeRecord]:
    out: list[IncomeRecord] = []
    for doc, fields, _ in extractions:
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)

        if isinstance(fields, PaystubFields):
            out.append(
                IncomeRecord(
                    kind=IncomeKind.W2_WAGES,
                    amount=Sourced[float](value=fields.gross_pay_current, provenance=prov),
                    period_start=fields.period_begin_date,
                    period_end=fields.period_end_date,
                    period_label=f"Pay period {fields.period_begin_date} to {fields.period_end_date}",
                    employer_name=fields.employer_name,
                    notes="paystub current period gross",
                )
            )
        elif isinstance(fields, W2Fields):
            out.append(
                IncomeRecord(
                    kind=IncomeKind.W2_BOX1,
                    amount=Sourced[float](value=fields.box_1_wages, provenance=prov),
                    period_label=f"{fields.tax_year} annual",
                    employer_name=fields.employer_name,
                    notes="W-2 box 1 (taxable wages, after pre-tax deductions)",
                )
            )
            if fields.box_3_ss_wages is not None:
                out.append(
                    IncomeRecord(
                        kind=IncomeKind.SOCIAL_SECURITY_WAGES,
                        amount=Sourced[float](value=fields.box_3_ss_wages, provenance=prov),
                        period_label=f"{fields.tax_year} annual",
                        employer_name=fields.employer_name,
                        notes="W-2 box 3 (Social Security wages, pre-deduction)",
                    )
                )
        elif isinstance(fields, EvoeFields):
            for annual in fields.annual_income:
                if annual.total is not None:
                    out.append(
                        IncomeRecord(
                            kind=IncomeKind.W2_WAGES,
                            amount=Sourced[float](value=annual.total, provenance=prov),
                            period_label=f"{annual.year} annual"
                            + (" (YTD)" if annual.is_year_to_date else ""),
                            employer_name=fields.employer_name,
                            notes="EVOE annual income summary — total",
                        )
                    )
                if annual.commissions:
                    out.append(
                        IncomeRecord(
                            kind=IncomeKind.COMMISSION,
                            amount=Sourced[float](value=annual.commissions, provenance=prov),
                            period_label=f"{annual.year} annual",
                            employer_name=fields.employer_name,
                            notes="EVOE annual income summary — commissions",
                        )
                    )
        elif isinstance(fields, ScheduleCFields):
            out.append(
                IncomeRecord(
                    kind=IncomeKind.SELF_EMPLOYMENT_NET,
                    amount=Sourced[float](value=fields.line_31_net_profit, provenance=prov),
                    period_label=f"{fields.tax_year} annual",
                    employer_name=fields.business_name,
                    notes="Schedule C line 31 (net profit)",
                )
            )
            if fields.line_1_gross_receipts is not None:
                out.append(
                    IncomeRecord(
                        kind=IncomeKind.SELF_EMPLOYMENT_GROSS,
                        amount=Sourced[float](
                            value=fields.line_1_gross_receipts, provenance=prov
                        ),
                        period_label=f"{fields.tax_year} annual",
                        employer_name=fields.business_name,
                        notes="Schedule C line 1 (gross receipts)",
                    )
                )
        elif isinstance(fields, BankStatementFields):
            if fields.interest_paid:
                out.append(
                    IncomeRecord(
                        kind=IncomeKind.INTEREST,
                        amount=Sourced[float](value=fields.interest_paid, provenance=prov),
                        period_start=fields.statement_period_start,
                        period_end=fields.statement_period_end,
                        period_label=f"{fields.statement_period_start} to {fields.statement_period_end}",
                        employer_name=fields.institution_name,
                        notes="bank statement interest paid",
                    )
                )
    return out


def _build_accounts(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> list[Account]:
    out: list[Account] = []
    for doc, fields, _ in extractions:
        if not isinstance(fields, BankStatementFields):
            continue
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)
        kind = (
            AccountKind.CHECKING
            if doc.doc_type is DocumentType.BANK_STATEMENT_CHECKING
            else AccountKind.SAVINGS
            if doc.doc_type is DocumentType.BANK_STATEMENT_SAVINGS
            else AccountKind.OTHER
        )
        out.append(
            Account(
                institution_name=Sourced[str](value=fields.institution_name, provenance=prov),
                kind=kind,
                account_number=Sourced[str](value=fields.account_number, provenance=prov),
                holders=fields.account_holders,
                statement_period_start=fields.statement_period_start,
                statement_period_end=fields.statement_period_end,
                beginning_balance=Sourced[float](value=fields.beginning_balance, provenance=prov),
                ending_balance=Sourced[float](value=fields.ending_balance, provenance=prov),
                interest_rate=(
                    Sourced[float](value=fields.interest_rate, provenance=prov)
                    if fields.interest_rate is not None
                    else None
                ),
                apy=(
                    Sourced[float](value=fields.apy, provenance=prov)
                    if fields.apy is not None
                    else None
                ),
            )
        )
    return out


def _build_loan(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> Loan | None:
    cd_fields: tuple[Document, ClosingDisclosureFields] | None = None
    f1008_fields: tuple[Document, Form1008Fields] | None = None
    for doc, fields, _ in extractions:
        if isinstance(fields, ClosingDisclosureFields):
            cd_fields = (doc, fields)
        elif isinstance(fields, Form1008Fields):
            f1008_fields = (doc, fields)

    if not cd_fields and not f1008_fields:
        return None

    loan_id_candidates: list[Sourced[str]] = []
    loan_amount_candidates: list[Sourced[float]] = []
    note_rate: Sourced[float] | None = None
    sale_price: Sourced[float] | None = None
    appraised_value: Sourced[float] | None = None
    ltv: Sourced[float] | None = None
    loan_terms: list[Sourced[LoanTerm]] = []
    purpose: Sourced[str] | None = None
    loan_type: Sourced[str] | None = None
    amortization_type: Sourced[str] | None = None
    closing_date = None
    disbursement_date = None
    settlement_agent: Sourced[str] | None = None
    lender_name: Sourced[str] | None = None
    co_borrowers: list[str] = []

    if cd_fields:
        cd_doc, cd = cd_fields
        cd_prov = Provenance(document_id=cd_doc.id, page=1, confidence=cd_doc.classifier_confidence)
        if cd.loan_id:
            loan_id_candidates.append(Sourced[str](value=cd.loan_id, provenance=cd_prov))
        if cd.purpose:
            purpose = Sourced[str](value=cd.purpose, provenance=cd_prov)
        if cd.loan_type:
            loan_type = Sourced[str](value=cd.loan_type, provenance=cd_prov)
        if cd.product:
            amortization_type = Sourced[str](value=cd.product, provenance=cd_prov)
        if cd.lender_name:
            lender_name = Sourced[str](value=cd.lender_name, provenance=cd_prov)
        if cd.settlement_agent:
            settlement_agent = Sourced[str](value=cd.settlement_agent, provenance=cd_prov)
        if cd.closing_date:
            closing_date = Sourced[Any](value=cd.closing_date, provenance=cd_prov)
        if cd.disbursement_date:
            disbursement_date = Sourced[Any](value=cd.disbursement_date, provenance=cd_prov)
        if cd.sale_price is not None:
            sale_price = Sourced[float](value=cd.sale_price, provenance=cd_prov)
        for term in cd.loan_terms:
            loan_terms.append(Sourced[LoanTerm](value=term, provenance=cd_prov))
            if term.description.lower() == "loan amount" and term.amount is not None:
                loan_amount_candidates.append(
                    Sourced[float](value=term.amount, provenance=cd_prov)
                )
        if cd.borrower_names:
            co_borrowers = [n for n in cd.borrower_names[1:]]

    if f1008_fields:
        f_doc, f = f1008_fields
        f_prov = Provenance(document_id=f_doc.id, page=1, confidence=f_doc.classifier_confidence)
        if f.seller_loan_number:
            loan_id_candidates.append(Sourced[str](value=f.seller_loan_number, provenance=f_prov))
        if f.loan_amount is not None:
            loan_amount_candidates.append(Sourced[float](value=f.loan_amount, provenance=f_prov))
        if f.note_rate is not None:
            note_rate = Sourced[float](value=f.note_rate, provenance=f_prov)
        if f.sales_price is not None and sale_price is None:
            sale_price = Sourced[float](value=f.sales_price, provenance=f_prov)
        if f.appraised_value is not None:
            appraised_value = Sourced[float](value=f.appraised_value, provenance=f_prov)
        if f.ltv is not None:
            ltv = Sourced[float](value=f.ltv, provenance=f_prov)
        if f.loan_purpose and purpose is None:
            purpose = Sourced[str](value=f.loan_purpose, provenance=f_prov)
        if f.loan_type and loan_type is None:
            loan_type = Sourced[str](value=f.loan_type, provenance=f_prov)
        if f.amortization_type and amortization_type is None:
            amortization_type = Sourced[str](value=f.amortization_type, provenance=f_prov)
        if f.co_borrower_name and f.co_borrower_name not in co_borrowers:
            co_borrowers.append(f.co_borrower_name)

    return Loan(
        loan_id=(
            MultiSourced[str](primary=loan_id_candidates[0], alternates=loan_id_candidates[1:])
            if loan_id_candidates
            else None
        ),
        purpose=purpose,
        loan_type=loan_type,
        amortization_type=amortization_type,
        loan_amount=(
            MultiSourced[float](
                primary=loan_amount_candidates[0],
                alternates=loan_amount_candidates[1:],
            )
            if loan_amount_candidates
            else None
        ),
        note_rate=note_rate,
        lender_name=lender_name,
        settlement_agent=settlement_agent,
        closing_date=closing_date,
        disbursement_date=disbursement_date,
        sale_price=sale_price,
        appraised_value=appraised_value,
        ltv=ltv,
        loan_terms=loan_terms,
        co_borrowers=co_borrowers,
    )


def _build_properties(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> list[Property]:
    out: list[Property] = []
    for doc, fields, _ in extractions:
        prov = Provenance(document_id=doc.id, page=1, confidence=doc.classifier_confidence)
        addr: Address | None = None
        legal: str | None = None
        parcel: str | None = None
        occupancy: str | None = None

        if isinstance(fields, ClosingDisclosureFields):
            addr = fields.property_address
        elif isinstance(fields, Form1008Fields):
            addr = fields.property_address
            occupancy = fields.occupancy_status
        elif isinstance(fields, TitleReportFields):
            addr = fields.property_address
            legal = fields.legal_description
            parcel = fields.parcel_id
        else:
            continue

        if not addr:
            continue
        out.append(
            Property(
                role="subject",
                address=Sourced[Address](value=addr, provenance=prov),
                legal_description=(
                    Sourced[str](value=legal, provenance=prov) if legal else None
                ),
                parcel_id=(Sourced[str](value=parcel, provenance=prov) if parcel else None),
                occupancy_status=(
                    Sourced[str](value=occupancy, provenance=prov) if occupancy else None
                ),
            )
        )
    return out


def _novel_field_flags(
    extractions: Sequence[tuple[Document, Any, list[NovelFieldHint]]],
) -> list[ExtractionFlag]:
    flags: list[ExtractionFlag] = []
    for doc, _, novel in extractions:
        for hint in novel:
            flags.append(
                ExtractionFlag(
                    id=f"flag-{uuid4().hex[:8]}",
                    kind=FlagKind.NOVEL_FIELD,
                    severity=FlagSeverity.INFO,
                    summary=(
                        f"{doc.doc_type.value}: novel field `{hint.field_name}` "
                        f"({hint.suggested_type}) — needs schema mapping"
                    ),
                    details={
                        "field_name": hint.field_name,
                        "suggested_type": hint.suggested_type,
                        "sample_value": hint.sample_value,
                        "notes": hint.notes,
                    },
                    documents=[doc.id],
                    field_path=hint.field_name,
                    detected_at=datetime.utcnow(),
                )
            )
    return flags


def _low_confidence_flags(docs_by_id: dict[str, Document]) -> list[ExtractionFlag]:
    return [
        ExtractionFlag(
            id=f"flag-{uuid4().hex[:8]}",
            kind=FlagKind.LOW_CONFIDENCE,
            severity=FlagSeverity.WARN,
            summary=f"Low classifier confidence ({doc.classifier_confidence:.2f}) for {doc.filename}",
            details={"classifier_confidence": doc.classifier_confidence},
            documents=[doc.id],
            field_path=None,
            detected_at=datetime.utcnow(),
        )
        for doc in docs_by_id.values()
        if doc.classifier_confidence < 0.6
    ]
