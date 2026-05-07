// Mirrors apps/extractor/src/extractor/schema.py.
// Hand-aligned for now; future iteration: codegen from Borrower's JSON Schema.

export type ISO8601 = string;
export type ISODate = string;

export interface Provenance {
  document_id: string;
  page: number;
  confidence: number;
  raw_text_excerpt?: string | null;
}

export interface Sourced<T> {
  value: T;
  provenance: Provenance;
}

export interface MultiSourced<T> {
  primary: Sourced<T>;
  alternates: Sourced<T>[];
}

export interface Address {
  line_1: string;
  line_2?: string | null;
  city: string;
  state: string;
  postal_code: string;
  country?: string;
}

export interface Contact {
  phone?: string | null;
  email?: string | null;
}

export interface PII {
  legal_name: MultiSourced<string>;
  date_of_birth?: MultiSourced<ISODate> | null;
  address: MultiSourced<Address>;
  contact: Contact;
}

export interface BorrowerIdentifiers {
  ssn?: MultiSourced<string> | null;
  aliases: Sourced<string>[];
}

export interface EmploymentRecord {
  employer_name: Sourced<string>;
  employer_address?: Sourced<Address> | null;
  job_title?: Sourced<string> | null;
  employment_status?: Sourced<string> | null;
  most_recent_start_date?: Sourced<ISODate> | null;
  original_hire_date?: Sourced<ISODate> | null;
  end_date?: Sourced<ISODate> | null;
  pay_frequency?: Sourced<string> | null;
  rate_of_pay?: Sourced<number> | null;
}

export type IncomeKind =
  | "w2_wages"
  | "w2_box1"
  | "social_security_wages"
  | "self_employment_net"
  | "self_employment_gross"
  | "overtime"
  | "commission"
  | "bonus"
  | "other"
  | "interest"
  | "dividends"
  | "rental"
  | "social_security_benefit"
  | "pension";

export interface IncomeRecord {
  kind: IncomeKind;
  amount: Sourced<number>;
  period_start?: ISODate | null;
  period_end?: ISODate | null;
  period_label?: string | null;
  employer_name?: string | null;
  notes?: string | null;
}

export type AccountKind = "checking" | "savings" | "other";

export interface Account {
  institution_name: Sourced<string>;
  kind: AccountKind;
  account_number: Sourced<string>;
  holders: string[];
  statement_period_start?: ISODate | null;
  statement_period_end?: ISODate | null;
  beginning_balance?: Sourced<number> | null;
  ending_balance?: Sourced<number> | null;
  interest_rate?: Sourced<number> | null;
  apy?: Sourced<number> | null;
}

export interface LoanTerm {
  description: string;
  amount?: number | null;
  can_increase_after_closing?: boolean | null;
}

export interface Loan {
  loan_id?: MultiSourced<string> | null;
  purpose?: Sourced<string> | null;
  loan_type?: Sourced<string> | null;
  amortization_type?: Sourced<string> | null;
  loan_amount?: MultiSourced<number> | null;
  note_rate?: Sourced<number> | null;
  loan_term_months?: Sourced<number> | null;
  lender_name?: Sourced<string> | null;
  settlement_agent?: Sourced<string> | null;
  closing_date?: Sourced<ISODate> | null;
  disbursement_date?: Sourced<ISODate> | null;
  sale_price?: Sourced<number> | null;
  appraised_value?: Sourced<number> | null;
  ltv?: Sourced<number> | null;
  loan_terms: Sourced<LoanTerm>[];
  co_borrowers: string[];
}

export interface Property {
  role: "subject" | "other";
  address: Sourced<Address>;
  legal_description?: Sourced<string> | null;
  parcel_id?: Sourced<string> | null;
  occupancy_status?: Sourced<string> | null;
}

export type DocumentType =
  | "paystub"
  | "w2"
  | "evoe"
  | "form_1040"
  | "schedule_1"
  | "schedule_c"
  | "bank_statement_checking"
  | "bank_statement_savings"
  | "closing_disclosure"
  | "title_report"
  | "letter_of_explanation"
  | "underwriting_transmittal_1008"
  | "unknown";

export interface Document {
  id: string;
  path: string;
  filename: string;
  page_count: number;
  sha256: string;
  doc_type: DocumentType;
  classifier_confidence: number;
  extracted_at: ISO8601;
  bytes: number;
}

export type FlagKind =
  | "novel_field"
  | "novel_doc_type"
  | "conflict"
  | "low_confidence"
  | "parsing_anomaly";
export type FlagSeverity = "info" | "warn" | "error";
export type FlagStatus = "open" | "ack" | "resolved" | "ignored";

export interface ExtractionFlag {
  id: string;
  kind: FlagKind;
  severity: FlagSeverity;
  summary: string;
  details: Record<string, unknown>;
  documents: string[];
  field_path?: string | null;
  detected_at: ISO8601;
  status: FlagStatus;
}

export interface ExtractionMeta {
  extracted_at: ISO8601;
  extractor_version: string;
  llm_provider: string;
  llm_model: string;
  corpus_path: string;
  duration_seconds: number;
}

export interface Borrower {
  id: string;
  pii: PII;
  identifiers: BorrowerIdentifiers;
  co_borrowers: PII[];
  employment: EmploymentRecord[];
  income: IncomeRecord[];
  accounts: Account[];
  loan: Loan | null;
  properties: Property[];
  source_documents: Document[];
  flags: ExtractionFlag[];
  extraction_meta: ExtractionMeta;
}
