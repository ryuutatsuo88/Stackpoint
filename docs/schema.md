# Data Model & Source Field Map

This is the canonical schema for the Loan 214 corpus. The Pydantic models in `apps/extractor/src/extractor/schema.py` are generated from (or hand-aligned to) this document; the TypeScript types in `apps/web/lib/types.ts` are derived from the same JSON Schema.

> **Why a markdown source-of-truth alongside Pydantic?** A markdown table is reviewable by humans (PMs, domain experts) without reading Python. The Pydantic file is what code uses; this file is what people argue about.

## High-level model

```
Borrower
├── pii: PII                        # canonical name, dob, address, contact
├── identifiers: BorrowerIdentifiers # SSN(s), aliases observed across docs
├── employment: list[EmploymentRecord]
├── income: list[IncomeRecord]      # one entry per source-doc-derived figure (no premature reconciliation)
├── accounts: list[Account]
├── loan: Loan | None
├── property: list[Property]        # subject + any others mentioned
├── source_documents: list[Document]
├── flags: list[ExtractionFlag]     # cross-doc inconsistencies + novel fields
└── extraction_meta: ExtractionMeta
```

Every field carries `Provenance = {document_id, page, confidence, raw_text_excerpt?}`. Fields that appear in multiple docs are stored as a list of `(value, provenance)` tuples — the UI picks a "primary" by rule (most recent / highest-confidence / underwriting-doc-prefers-1040, etc.) but never throws the alternates away.

## Document types (known)

| Type ID | Filename pattern | Notes |
|---|---|---|
| `paystub` | `Paystub- *` | Single-page, current period + YTD |
| `w2` | `W2 *` | One copy, may have multi-line box 12 |
| `evoe` | `EVOE *` | Equifax / The Work Number VOI; 3-year annual income summary |
| `form_1040` | `1040 *` | Form 1040 main |
| `schedule_1` | (bundled with 1040) | Additional Income & Adjustments |
| `schedule_c` | (bundled with 1040) | Self-employment P&L |
| `bank_statement_checking` | `Checking *` | Statement period, transactions, fees |
| `bank_statement_savings` | `Savings *` | Statement period, interest |
| `closing_disclosure` | `Closing_Disclosure*` | May be partial / non-CFPB-standard |
| `title_report` | `Title*` | ALTA Commitment 2021 v01.00 |
| `letter_of_explanation` | `Letter_of_Explanation*` | Free-text prose |
| `underwriting_transmittal_1008` | `document.pdf` (heuristic) | Fannie Form 1008 + Conditional Approval cover + conditions worksheet — added after corpus walk |

A document not matching any of these by classifier confidence threshold (>= 0.7) is tagged `unknown` and routed to the novelty pipeline.

## API constraint: structured-output schema complexity

The Anthropic structured-output API caps schemas at ~16 nullable / union-typed parameters per request. Several of the canonical `*Fields` models below exceed this — Form 1040, Form 1008, Paystub, Bank Statement. We work around it by splitting those into 2–3 sub-schemas (shards) defined in `apps/extractor/src/extractor/extractors.py` and merging the partial results into the canonical model. The canonical schema below stays untouched. See [`docs/design.md`](./design.md#multi-pass-extraction-working-around-the-structured-output-schema-limit) for the design discussion.

## Per-doc-type field inventory

Below is the inventory for each doc type, derived from a full read of every PDF in `documents/Loan Documents/Loan 214/`. Field names are snake_case Pydantic candidates.

### `paystub`
Header — `employer_name, employer_address`, employee block (`employee_name, employee_address, taxable_marital_status, federal_exemptions_allowances`).
Pay period — `period_begin_date, period_end_date, pay_date, basis_of_pay, advice_number`.
Earnings — `earnings: list[{type, rate, hours, current_amount, ytd_amount}]` (regular/overtime/commission/bonus); `total_work_hours_period, gross_pay_current, gross_pay_ytd`.
Other benefits — `other_benefits: list[{type, current, ytd}]`.
Deductions — `deductions_statutory: {federal_income_tax, state_tax, medicare_tax, social_security}` × {current, ytd}; `deductions_other: list[{name, current, ytd, pre_tax}]`.
Net — `net_pay_current, net_pay_residual_or_other, direct_deposit: list[{name, account_masked, transit_aba, amount}]`.

### `w2`
`tax_year, copy_designation, omb_number, control_number_d`.
Employer — `employer_ein_box_b, employer_name, employer_address`.
Employee — `employee_ssn_box_a, employee_name, employee_address`.
Box values — `box_1_wages_tips_other_comp` … `box_20_locality_name` (all numbered boxes, list-typed for box 12 codes, flag-typed for box 13).

### `evoe`
Header — `subject_name, subject_ssn_masked, current_as_of_date, provider, verification_type`.
Order — `verified_on_date, permissible_purpose, reference_number, tracking_number`.
Employer — `employer_name, employer_address_*`.
Employment — `division, employment_status, most_recent_start_date, original_hire_date, end_date, total_time_with_employer, job_title`.
Income — `rate_of_pay, pay_frequency, avg_hours_per_pay_period, pay_period_frequency, last_pay_increase_amount, next_pay_increase_amount, annual_income: list[{year, base_salary, overtime, commissions, bonus, other, total}]`.

### `form_1040` (per tax year — corpus has 2023 and 2024 in one PDF)
`tax_year, filing_status, taxpayer:{name, ssn}, spouse:{name, ssn}, address, dependents: list[{name, ssn, relationship, ctc_eligible, odc_eligible}]`.
Lines 1a–15 income, 16–24 tax/credits/payments, 25a–38 refund/owed, signature block (taxpayer/spouse occupations, dates), paid preparer block.

### `schedule_1` (paired with each 1040 year)
Part I additional income (lines 1–10); Part II adjustments (lines 11–26).

### `schedule_c` (paired with each 1040 year)
Header — `proprietor_name, proprietor_ssn, business_name, ein, naics_business_code, business_address, accounting_method, materially_participate`.
Part I income lines 1–7; Part II expenses lines 8–27 (each named); Part III COGS 33–42; Part IV vehicle 43–47; Part V `other_expenses: list[{description, amount}]`.

### `bank_statement_checking` / `bank_statement_savings`
Institution header, account holder block, account summary (`account_number, product_name, statement_period_*, apy, interest_rate, ytd_interest, beginning_balance, ending_balance, total_credits/debits, interest_paid, service_charges`).
`transactions: list[{trans_date, post_date, description, amount, balance}]`, `fees: list[…]`, `interest_rate_history: list[{date, rate}]`, NSF/overdraft summary fields.

### `closing_disclosure`
Closing info (`date_issued, closing_date, disbursement_date, settlement_agent, file_number, property_address, sale_price`).
Transaction info (borrower/seller/lender names).
Loan info (`loan_term, purpose, product, loan_type, loan_id, mic_number`).
`loan_terms: list[{description, amount, can_increase_after_closing}]`, `projected_payments: list[{period, p_and_i, mortgage_insurance, estimated_escrow}]`, `estimated_closing_costs, estimated_cash_to_close`.

> Note: this corpus's CD is a **partial** CD, not a standard 5-page CFPB form. Schema accepts subsets.

### `title_report` (ALTA Commitment 2021)
Schedule A — `issuing_agent, alta_registry_id, loan_id_number, commitment_number, file_number, property_address, commitment_date, policies_to_be_issued: list[{policy_type, proposed_insured, proposed_amount, estate_or_interest}], current_vesting, legal_description_reference, countersigned_by_name, countersignature_present`.
Schedule B-I — `requirements: list[{number, text}]`, structured sub-extracts: `prior_mortgage_to_release, probate_case_number, decedent_name, prior_year_property_tax`.
Schedule B-II — `exceptions: list[{number, text}]`.
Exhibit A — `legal_description, county, state`.
Boilerplate (pp. 1-4) — `conditions_text` blob (low extraction priority).
Tax estimator screenshots (pp. 11-12) — image-rendered; OCR optional, fields: `tax_estimator_source_url, soh_assessed_value, exemption_value, taxable_value, school_taxable_value, estimated_tax, homestead_exemption, screenshot_timestamp`.

### `letter_of_explanation`
`letter_date, salutation, subject_topic, referenced_event_date, explanation_body, signer:{name, address, phone, email}, disclaimer_footer`.

### `underwriting_transmittal_1008` (NEW — added after corpus walk)
Section I (borrower & property) — `borrower_name, total_number_of_borrowers, property_address, occupancy_status, sales_price, appraised_value, property_type, project_classification, property_rights, project_name`.
Section II (mortgage) — `loan_type, amortization_type, loan_purpose, lien_position, subordinate_financing_amount, loan_amount, note_rate, loan_term_months, mortgage_originator, temporary_buydown, broker_correspondent_name`.
Section III (underwriting) — `underwriter_name, appraiser_*, stable_monthly_income:{borrower_1..4, combined_other_income, rental_subject, net_rental_other, total}, at_least_one_borrower_self_employed_flag, ltv:{ltv, cltv, hcltv}, proposed_monthly_payments:{…}, borrower_funds_to_close:{…}, qualifying_ratios, qualifying_rate, risk_assessment:{manual, aus, du, lpa, aus_recommendation, du_case_id, lpa_doc_class, representative_credit_score}, level_of_property_review, appraisal_form_number, escrow_t_and_i, affordable_housing_initiative, underwriter_comments`.
Section IV — `seller_name, seller_address, seller_loan_number, contact_*, investor_loan_number`.
Addendum — `co_borrower_continuation: list[{name, ssn, caivrs_number, ldp_sam}]`.
Conditional Approval cover — `lender_account_label, broker_block, lender_block, borrower_block:{name, credit_scores: list[3], co_borrower_*}, underwriting_block:{approved_date, must_close_by_date, underwriter, processor}, lock:{note_rate, qual_rate, expires}, loan_information:{...}, underwriter_signature_block`.
Conditions worksheet — `prior_to_approval_conditions, prior_to_docs_conditions, prior_to_funding_conditions, at_closing_conditions` (often blank).

## Cross-document reconciliation rules

The aggregator does NOT collapse conflicting facts; it picks a **primary** value for the UI and preserves alternates with provenance.

| Field | Primary source (preferred) | Fallback chain |
|---|---|---|
| Borrower legal name | 1040 taxpayer name | W-2 → EVOE → CD → bank stmt |
| SSN | 1040 (full SSN) | Bank stmt → W-2 (full visible) → EVOE (masked) |
| Current address | Most recent paystub | W-2 → 1040 → bank stmt |
| Subject property address | Closing Disclosure | Form 1008 → Title Report (only if matches) |
| W-2 annual wages | W-2 box 1 | EVOE total annual |
| Self-employment net income | Schedule C line 31 | 1040 Schedule 1 line 3 |
| Loan amount | Closing Disclosure loan_terms | Form 1008 loan_amount |
| Account balance (checking/savings) | Most recent statement ending balance | n/a |

## Cross-document consistency checks (emitted as flags)

The aggregator runs these and emits `ExtractionFlag(kind="conflict", …)` entries, surfaced in `/flags` UI:

1. **Subject property address mismatch** — across CD, Form 1008, Title Report. *(Triggers in the current corpus: 3 distinct addresses.)*
2. **SSN mismatch** — same person across docs has different SSNs. *(Triggers: Mary 500-22-2000 on 1040 vs 500-60-2222 on Form 1008.)*
3. **Loan ID mismatch** — same loan referenced with different IDs across docs. *(Triggers: TEST250700110 vs TEST250700114.)*
4. **Borrower-of-record mismatch** — Title Report parties (proposed insureds, current vesting) don't intersect with the borrower set on Form 1008/CD. *(Triggers: VanAssen family on title commitment.)*
5. **Income reconciliation drift** — W-2 box 1 vs EVOE annual_income.total > $X tolerance (configurable). *(Expected to trigger because of pre-tax 401k/HSA — useful as an explained-but-flagged case.)*
6. **Net pay arithmetic** — paystub gross − total deductions ≠ net pay. *(May trigger because of unlabeled secondary deposit line.)*

## Novel-field detection

After per-doc-type extraction, an open-ended pass asks the LLM: "List every structured field present in this document that is NOT already in this schema." Diff result against the canonical schema → emit `ExtractionFlag(kind="novel_field", …)`.

A novel field gets:
- `field_name` (LLM-suggested snake_case)
- `sample_value` (first observed value, redacted if PII)
- `suggested_type` (`str | int | float | date | bool | list | object`)
- `source: Provenance`
- `status: "needs_mapping" | "ignored" | "promoted_to_schema"`

UI exposes these on `/flags`. Promoting a novel field into the canonical schema is a code change (edit `schema.md` + `schema.py` + add an extractor field) but the flag tells you it's needed.

## Identity model — `ExtractionFlag`

```python
class ExtractionFlag(BaseModel):
    id: str
    kind: Literal["novel_field", "novel_doc_type", "conflict", "low_confidence"]
    severity: Literal["info", "warn", "error"]
    summary: str                      # human-readable one-liner
    details: dict                     # kind-specific payload
    documents: list[str]              # document_ids involved
    field_path: str | None            # e.g. "borrower.pii.ssn"
    detected_at: datetime
    status: Literal["open", "ack", "resolved", "ignored"] = "open"
```
