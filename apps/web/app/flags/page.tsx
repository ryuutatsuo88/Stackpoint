import Link from "next/link";
import { repository } from "@/lib/repository";
import { FlagBadge } from "@/components/FlagBadge";

export const dynamic = "force-dynamic";

export default async function FlagsPage() {
  const borrowers = await repository.list();
  const all = borrowers.flatMap((b) =>
    b.flags.map((f) => ({ borrower: b, flag: f })),
  );
  all.sort((a, b) => severityOrder(b.flag.severity) - severityOrder(a.flag.severity));

  return (
    <main className="space-y-6">
      <header>
        <h1 className="font-display text-4xl tracking-tight text-white">Flags</h1>
        <p className="mt-2 max-w-2xl muted">
          Things that need a human eye — schema-novel fields, cross-document
          conflicts, low-confidence extractions.
        </p>
      </header>

      {all.length === 0 ? (
        <div className="card p-10 text-center muted text-sm">No flags.</div>
      ) : (
        <ul className="space-y-3">
          {all.map(({ borrower, flag }) => (
            <li key={flag.id} className="card p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <div className="flex items-center gap-2">
                  <FlagBadge flag={flag} />
                  <Link
                    href={`/borrowers/${borrower.id}`}
                    className="text-sm font-medium text-white hover:text-accent-400"
                  >
                    {borrower.pii.legal_name.primary.value}
                  </Link>
                  {flag.field_path && (
                    <span className="text-xs muted">· {flag.field_path}</span>
                  )}
                </div>
                <span className="text-xs muted">
                  {flag.documents.length} doc{flag.documents.length === 1 ? "" : "s"}
                </span>
              </div>
              <p className="value mt-2 text-sm">{flag.summary}</p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function severityOrder(s: string): number {
  return { error: 3, warn: 2, info: 1 }[s as "error" | "warn" | "info"] ?? 0;
}
