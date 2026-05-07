// Display formatters. Centralized so units don't drift across pages.

export function formatCurrency(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function formatPercent(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(2).replace(/\.00$/, "")}%`;
}

export function formatDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatAddress(a: {
  line_1: string;
  line_2?: string | null;
  city: string;
  state: string;
  postal_code: string;
}): string {
  const lines = [a.line_1];
  if (a.line_2) lines.push(a.line_2);
  lines.push(`${a.city}, ${a.state} ${a.postal_code}`);
  return lines.join(", ");
}

export function humanizeDocType(t: string): string {
  const map: Record<string, string> = {
    paystub: "Paystub",
    w2: "W-2",
    evoe: "EVOE",
    form_1040: "Form 1040",
    schedule_c: "Schedule C",
    bank_statement_checking: "Checking statement",
    bank_statement_savings: "Savings statement",
    closing_disclosure: "Closing Disclosure",
    title_report: "Title Report",
    letter_of_explanation: "Letter of Explanation",
    underwriting_transmittal_1008: "Form 1008",
    unknown: "Unknown",
  };
  return map[t] ?? t;
}

export function humanizeIncomeKind(k: string): string {
  const map: Record<string, string> = {
    w2_wages: "W-2 wages",
    w2_box1: "W-2 box 1 (taxable)",
    social_security_wages: "SS wages (box 3)",
    self_employment_net: "Self-employment (net)",
    self_employment_gross: "Self-employment (gross)",
    overtime: "Overtime",
    commission: "Commission",
    bonus: "Bonus",
    interest: "Interest",
    dividends: "Dividends",
    rental: "Rental",
    other: "Other",
  };
  return map[k] ?? k;
}
