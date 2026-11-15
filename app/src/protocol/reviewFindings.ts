/** `/code-review` bulguları (#214, Claude Code ReportFindings): çekirdeğin `bulgular` alanı. */
export interface ReviewFinding {
  file: string;
  line: number;
  summary: string;
  failureScenario: string;
  shortSummary?: string;
  category?: string;
  verdict?: "CONFIRMED" | "PLAUSIBLE";
}

/** Çekirdekle aynı tavan (`code_review_findings.MAX_FINDINGS`). */
const MAX_FINDINGS = 32;

function finding(value: unknown): ReviewFinding | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const data = value as Record<string, unknown>;
  if (typeof data.file !== "string" || !data.file || typeof data.summary !== "string" ||
      typeof data.failure_scenario !== "string" || typeof data.line !== "number" ||
      !Number.isSafeInteger(data.line) || data.line < 1) return null;
  return {
    file: data.file,
    line: data.line,
    summary: data.summary,
    failureScenario: data.failure_scenario,
    ...(typeof data.short_summary === "string" && data.short_summary ? {shortSummary: data.short_summary} : {}),
    ...(typeof data.category === "string" && data.category ? {category: data.category} : {}),
    ...(data.verdict === "CONFIRMED" || data.verdict === "PLAUSIBLE" ? {verdict: data.verdict} : {}),
  };
}

/** Alan yoksa `undefined` (kart çizilmez); boş dizi "bulgu yok" demektir. Bozuk öğe atlanır. */
export function decodeReviewFindings(value: unknown): ReviewFinding[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map(finding).filter((item): item is ReviewFinding => item !== null).slice(0, MAX_FINDINGS);
}
