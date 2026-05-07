import Link from "next/link";
import { notFound } from "next/navigation";
import { repository } from "@/lib/repository";
import {
  formatCurrency,
  formatPercent,
  formatDate,
  formatAddress,
  humanizeDocType,
  humanizeIncomeKind,
} from "@/lib/format";
import { FieldRow, multiToFieldRowProps } from "@/components/FieldRow";
import { FlagBadge } from "@/components/FlagBadge";
import { ProvenancePill } from "@/components/Provenance";

export const dynamic = "force-dynamic";

export default async function BorrowerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const b = await repository.get(id);
  if (!b) notFound();

  const docs = b.source_documents;

  return (
    <main className="space-y-10">
      <header>
        <Link
          href="/"
          className="text-sm text-navy-300 transition hover:text-white"
        >
          ← All borrowers
        </Link>
        <h1 className="mt-3 font-display text-5xl tracking-tight text-white">
          {b.pii.legal_name.primary.value}
        </h1>
        <p className="mt-2 muted">
          {formatAddress(b.pii.address.primary.value)}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {b.flags.map((f) => (
            <FlagBadge key={f.id} flag={f} />
          ))}
        </div>
      </header>

      {/* PII + identifiers */}
      <Section title="Identity">
        <FieldRow
          label="Legal name"
          {...multiToFieldRowProps(b.pii.legal_name, (v) => v)}
          documents={docs}
        />
        <FieldRow
          label="Address"
          {...multiToFieldRowProps(b.pii.address, (v) => formatAddress(v))}
          documents={docs}
        />
        <FieldRow
          label="SSN"
          {...multiToFieldRowProps(b.identifiers.ssn ?? null, (v) => v)}
          documents={docs}
        />
        {(b.pii.contact.phone || b.pii.contact.email) && (
          <FieldRow
            label="Contact"
            value={
              [b.pii.contact.phone, b.pii.contact.email]
                .filter(Boolean)
                .join(" · ") || "—"
            }
            documents={docs}
          />
        )}
      </Section>

      {/* Income */}
      <Section
        title="Income history"
        meta={`${b.income.length} record${b.income.length === 1 ? "" : "s"}`}
      >
        {b.income.length === 0 ? (
          <p className="muted py-3 text-sm">No income records.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5 text-left">
                  <th className="label py-2 font-normal">Source</th>
                  <th className="label py-2 font-normal">Period</th>
                  <th className="label py-2 font-normal">Employer</th>
                  <th className="label py-2 text-right font-normal">Amount</th>
                  <th className="label py-2 font-normal">From</th>
                </tr>
              </thead>
              <tbody>
                {b.income.map((i, idx) => (
                  <tr key={idx} className="border-b border-white/5 last:border-0">
                    <td className="py-3 value font-medium">
                      {humanizeIncomeKind(i.kind)}
                    </td>
                    <td className="py-3 muted">{i.period_label || "—"}</td>
                    <td className="py-3 muted">{i.employer_name || "—"}</td>
                    <td className="py-3 text-right value font-medium">
                      {formatCurrency(i.amount.value)}
                    </td>
                    <td className="py-3">
                      <ProvenancePill
                        provenance={i.amount.provenance}
                        documents={docs}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Accounts */}
      {b.accounts.length > 0 && (
        <Section title="Accounts" meta={`${b.accounts.length}`}>
          <div className="grid gap-3 md:grid-cols-2">
            {b.accounts.map((a, idx) => (
              <div key={idx} className="card-tight p-4">
                <div className="flex items-baseline justify-between">
                  <div>
                    <div className="value font-medium">
                      {a.institution_name.value}
                    </div>
                    <div className="text-xs muted capitalize">{a.kind}</div>
                  </div>
                  <ProvenancePill
                    provenance={a.institution_name.provenance}
                    documents={docs}
                  />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="label">Account</div>
                    <div className="value mt-0.5 font-mono text-xs">
                      {maskAccount(a.account_number.value)}
                    </div>
                  </div>
                  <div>
                    <div className="label">Ending balance</div>
                    <div className="value mt-0.5 font-medium">
                      {formatCurrency(a.ending_balance?.value ?? null)}
                    </div>
                  </div>
                </div>
                {a.holders.length > 0 && (
                  <div className="mt-2 text-xs muted">
                    Holders: {a.holders.join(", ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Loan */}
      {b.loan && (
        <Section title="Loan">
          <FieldRow
            label="Loan ID"
            {...multiToFieldRowProps(b.loan.loan_id ?? null, (v) => v)}
            documents={docs}
          />
          <FieldRow
            label="Amount"
            {...multiToFieldRowProps(b.loan.loan_amount ?? null, (v) =>
              formatCurrency(v),
            )}
            documents={docs}
          />
          {b.loan.note_rate && (
            <FieldRow
              label="Note rate"
              value={formatPercent(b.loan.note_rate.value / 100)}
              provenance={b.loan.note_rate.provenance}
              documents={docs}
            />
          )}
          {b.loan.purpose && (
            <FieldRow
              label="Purpose"
              value={b.loan.purpose.value}
              provenance={b.loan.purpose.provenance}
              documents={docs}
            />
          )}
          {b.loan.loan_type && (
            <FieldRow
              label="Type"
              value={b.loan.loan_type.value}
              provenance={b.loan.loan_type.provenance}
              documents={docs}
            />
          )}
          {b.loan.lender_name && (
            <FieldRow
              label="Lender"
              value={b.loan.lender_name.value}
              provenance={b.loan.lender_name.provenance}
              documents={docs}
            />
          )}
          {b.loan.closing_date && (
            <FieldRow
              label="Closing date"
              value={formatDate(b.loan.closing_date.value)}
              provenance={b.loan.closing_date.provenance}
              documents={docs}
            />
          )}
          {b.loan.sale_price && (
            <FieldRow
              label="Sale price"
              value={formatCurrency(b.loan.sale_price.value)}
              provenance={b.loan.sale_price.provenance}
              documents={docs}
            />
          )}
          {b.loan.ltv && (
            <FieldRow
              label="LTV"
              value={formatPercent(b.loan.ltv.value / 100)}
              provenance={b.loan.ltv.provenance}
              documents={docs}
            />
          )}
        </Section>
      )}

      {/* Properties */}
      {b.properties.length > 0 && (
        <Section
          title="Properties"
          meta={
            new Set(b.properties.map((p) => formatAddress(p.address.value)))
              .size > 1
              ? `${b.properties.length} addresses observed — see flags`
              : undefined
          }
        >
          {b.properties.map((p, idx) => (
            <div key={idx} className="border-b border-white/5 py-3 last:border-0">
              <div className="flex items-baseline justify-between">
                <div className="value font-medium">
                  {formatAddress(p.address.value)}
                </div>
                <ProvenancePill
                  provenance={p.address.provenance}
                  documents={docs}
                />
              </div>
              {p.legal_description && (
                <div className="mt-1 text-xs muted">
                  Legal: {p.legal_description.value.slice(0, 200)}
                </div>
              )}
            </div>
          ))}
        </Section>
      )}

      {/* Flags */}
      {b.flags.length > 0 && (
        <Section title="Flags" meta={`${b.flags.length}`}>
          <ul className="space-y-3">
            {b.flags.map((f) => (
              <li
                key={f.id}
                className="rounded-lg border border-white/5 bg-white/[0.02] p-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <FlagBadge flag={f} />
                      <span className="text-xs muted">{f.field_path}</span>
                    </div>
                    <p className="value mt-2 text-sm">{f.summary}</p>
                  </div>
                </div>
                {f.details && Object.keys(f.details).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-navy-300 hover:text-white">
                      Details
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-white/5 bg-navy-950 p-3 text-[11px] text-navy-200">
                      {JSON.stringify(f.details, null, 2)}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Source documents */}
      <Section
        title="Source documents"
        meta={`${docs.length} files extracted`}
      >
        <ul className="grid gap-2 md:grid-cols-2">
          {docs.map((d) => (
            <li
              key={d.id}
              className="flex items-baseline justify-between gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <div className="min-w-0">
                <div className="value truncate font-medium">{d.filename}</div>
                <div className="text-xs muted">
                  {humanizeDocType(d.doc_type)} · {d.page_count} pp ·{" "}
                  {(d.classifier_confidence * 100).toFixed(0)}% conf
                </div>
              </div>
              <span className="font-mono text-[10px] text-navy-300">
                {d.id}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      {/* Run metadata */}
      <p className="text-center text-xs muted">
        Extracted {formatDate(b.extraction_meta.extracted_at)} · provider{" "}
        {b.extraction_meta.llm_provider}/{b.extraction_meta.llm_model} ·{" "}
        {b.extraction_meta.duration_seconds.toFixed(1)}s
      </p>
    </main>
  );
}

function Section({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-6">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="font-display text-2xl text-white">{title}</h2>
        {meta && <span className="text-xs muted">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

function maskAccount(num: string): string {
  if (num.length <= 4) return `••••${num}`;
  return `${num.slice(0, -4).replace(/./g, "•")}${num.slice(-4)}`;
}
