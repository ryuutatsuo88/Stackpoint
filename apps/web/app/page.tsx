import Link from "next/link";
import { repository } from "@/lib/repository";
import { formatCurrency, formatAddress } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const borrowers = await repository.list();

  return (
    <main>
      <section className="mb-10">
        <h1 className="font-display text-4xl tracking-tight text-white">
          Borrowers
        </h1>
        <p className="mt-2 max-w-2xl muted">
          Structured records extracted from raw loan documents. Every value is
          traceable to its source PDF and page.
        </p>
      </section>

      {borrowers.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {borrowers.map((b) => {
            const totalIncome = b.income
              .filter((i) => i.kind === "w2_box1" || i.kind === "self_employment_net")
              .reduce((sum, i) => sum + i.amount.value, 0);
            const conflicts = b.flags.filter((f) => f.kind === "conflict").length;
            return (
              <li key={b.id}>
                <Link
                  href={`/borrowers/${b.id}`}
                  className="card block p-6 transition hover:border-accent-500/40"
                >
                  <div className="flex items-baseline justify-between">
                    <h2 className="font-display text-2xl text-white">
                      {b.pii.legal_name.primary.value}
                    </h2>
                    <span className="text-xs text-navy-300">{b.id}</span>
                  </div>
                  <p className="mt-1 text-sm muted">
                    {formatAddress(b.pii.address.primary.value)}
                  </p>

                  <div className="mt-5 grid grid-cols-3 gap-4 border-t border-white/5 pt-4 text-sm">
                    <div>
                      <div className="label">Annual income</div>
                      <div className="value mt-1 font-medium">
                        {totalIncome > 0 ? formatCurrency(totalIncome) : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="label">Source docs</div>
                      <div className="value mt-1 font-medium">
                        {b.source_documents.length}
                      </div>
                    </div>
                    <div>
                      <div className="label">Flags</div>
                      <div className="mt-1">
                        {b.flags.length === 0 ? (
                          <span className="value font-medium">none</span>
                        ) : (
                          <span className="font-medium text-white">
                            {b.flags.length}
                            {conflicts > 0 && (
                              <span className="ml-2 pill pill-error">
                                {conflicts} conflict{conflicts === 1 ? "" : "s"}
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

function EmptyState() {
  return (
    <div className="card p-12 text-center">
      <h2 className="font-display text-2xl text-white">No records yet</h2>
      <p className="muted mx-auto mt-2 max-w-md text-sm">
        Run the extractor to populate this view:
      </p>
      <pre className="mx-auto mt-4 inline-block rounded-md border border-white/10 bg-navy-950 px-4 py-2 text-left text-xs text-accent-400">
        cd apps/extractor && uv run extractor run --corpus ../../documents
      </pre>
    </div>
  );
}
