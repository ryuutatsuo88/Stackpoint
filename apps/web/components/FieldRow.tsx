import type { Document, Sourced, MultiSourced } from "@/lib/types";
import { ProvenancePill } from "./Provenance";

interface Props {
  label: string;
  value: React.ReactNode;
  provenance?: Sourced<unknown>["provenance"];
  documents?: Document[];
  alternates?: { value: React.ReactNode; provenance: Sourced<unknown>["provenance"] }[];
}

export function FieldRow({
  label,
  value,
  provenance,
  documents = [],
  alternates = [],
}: Props) {
  return (
    <div className="grid grid-cols-12 gap-3 border-b border-white/5 py-3 last:border-0">
      <div className="col-span-3 label">{label}</div>
      <div className="col-span-9 text-sm">
        <div className="flex flex-wrap items-center gap-3">
          <span className="value font-medium">{value || <span className="muted">—</span>}</span>
          {provenance && <ProvenancePill provenance={provenance} documents={documents} />}
        </div>
        {alternates.length > 0 && (
          <div className="mt-2 space-y-1">
            {alternates.map((alt, i) => (
              <div key={i} className="flex flex-wrap items-center gap-3 text-xs muted">
                <span>also: {alt.value}</span>
                <ProvenancePill provenance={alt.provenance} documents={documents} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function multiToFieldRowProps<T>(
  field: MultiSourced<T> | null | undefined,
  render: (v: T) => React.ReactNode,
): { value: React.ReactNode; provenance?: Sourced<unknown>["provenance"]; alternates: Props["alternates"] } {
  if (!field) return { value: "—", alternates: [] };
  return {
    value: render(field.primary.value),
    provenance: field.primary.provenance,
    alternates: field.alternates.map((a) => ({
      value: render(a.value),
      provenance: a.provenance,
    })),
  };
}
