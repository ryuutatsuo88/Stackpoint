import type { ExtractionFlag } from "@/lib/types";

const styles: Record<ExtractionFlag["severity"], string> = {
  info: "pill pill-info",
  warn: "pill pill-warn",
  error: "pill pill-error",
};

const kindLabel: Record<ExtractionFlag["kind"], string> = {
  conflict: "Conflict",
  novel_field: "Novel field",
  novel_doc_type: "Novel doc type",
  low_confidence: "Low confidence",
  parsing_anomaly: "Parsing anomaly",
};

export function FlagBadge({ flag }: { flag: ExtractionFlag }) {
  return (
    <span className={styles[flag.severity]}>
      <span className="font-medium">{kindLabel[flag.kind]}</span>
    </span>
  );
}
