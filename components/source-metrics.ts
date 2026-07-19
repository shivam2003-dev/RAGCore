import type { SourceMetric } from "@/lib/cvum-api";

const sourceLabels: Record<string, string> = {
  jira: "Jira",
  confluence: "Confluence",
  web: "Web",
  md: "Markdown uploads",
  txt: "Text uploads",
  pdf: "PDF uploads",
  docx: "Word uploads",
  csv: "CSV uploads",
  html: "HTML uploads",
};

export function sourceFamily(source: Pick<SourceMetric, "name" | "source_type">) {
  const type = source.source_type.toLowerCase();
  const name = source.name.toLowerCase();
  if (type.includes("jira") || name.includes("jira") || name.includes("devo") || name.includes("cvir")) return "jira";
  if (type.includes("confluence") || name.includes("confluence") || name.includes("sre")) return "confluence";
  if (type.includes("web") || name.includes("web")) return "web";
  return type || "knowledge";
}

export function sourceFamilyLabel(family: string) {
  return sourceLabels[family] ?? family.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function aggregateSourceMix(sources: SourceMetric[], valueKey: "documents" | "ready_documents" = "ready_documents") {
  const totals = new Map<string, number>();
  for (const source of sources) {
    const family = sourceFamily(source);
    totals.set(family, (totals.get(family) ?? 0) + source[valueKey]);
  }
  return Array.from(totals.entries())
    .map(([family, value]) => ({ family, label: sourceFamilyLabel(family), value }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value);
}
