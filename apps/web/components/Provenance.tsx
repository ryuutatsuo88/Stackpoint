import type { Provenance as ProvenanceT, Document as DocumentT } from "@/lib/types";

export function ProvenancePill({
  provenance,
  documents,
}: {
  provenance: ProvenanceT;
  documents: DocumentT[];
}) {
  const doc = documents.find((d) => d.id === provenance.document_id);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border border-white/5 bg-white/[0.03] px-2 py-0.5 text-[10px] uppercase tracking-wider text-navy-200"
      title={`${doc?.filename ?? provenance.document_id} · page ${provenance.page} · ${(provenance.confidence * 100).toFixed(0)}% conf`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-accent-500" />
      {doc ? abbrev(doc.filename) : provenance.document_id}
      <span className="text-navy-300">p{provenance.page}</span>
    </span>
  );
}

function abbrev(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, "");
  return stem.length > 22 ? stem.slice(0, 21) + "…" : stem;
}
