import {sirlariMaskele} from "./sirMaskesi";

/** Runtime kanıt özetini doğrular; model metni doğrulama kaynağı değildir. */
export interface DeliveryEvidence {
  kind: "supported" | "legacy" | "unsupported" | "invalid";
  verified: boolean | null;
  blocking: boolean;
  falseClaim: boolean;
  changed: string[];
  problems: string[];
  warnings?: string[];
  deliveryKind?: "code" | "artifact" | "observation";
  changedTotal: number | null;
  presentation?: "document";
  checks?: string[];
  unmeasured?: string[];
  advisories?: string[];
  changeSummary?: string[];
  detailsTruncated?: boolean;
  problemTotal?: number;
  criteriaTotal?: number;
  criteriaStatusCounts?: {passed: number; failed: number; unverified: number};
}

/** Çekirdeğin `completion_evidence.py` tavanları; aşan liste GEÇERSİZLİK değil, kesilir. */
const MAX_PATHS = 50;
const MAX_PROBLEMS = 10;
const MAX_TEXT = 500;
const MAX_SUMMARY = 50;
const MAX_BYTES = 32 * 1024;

function isTextList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

/** UTF-16 kesimi bir Unicode karakterini ortadan bölmesin. */
function publicText(value: string): string {
  return Array.from(sirlariMaskele(value)).slice(0, MAX_TEXT).join("");
}

function byteLength(value: DeliveryEvidence): number {
  return new TextEncoder().encode(JSON.stringify(value)).byteLength;
}

function unsupported(): DeliveryEvidence {
  return {kind: "unsupported", verified: null, blocking: false, falseClaim: false,
    changed: [], problems: [], changedTotal: null};
}

/**
 * Okunamayan kanıt fail-closed: "engelliyor" varsayılır; okunabilen `yanlis_iddia`
 * korunur. Ölçüldü (29 Ekim): eskiden blocking:false/falseClaim:false dönüyordu,
 * yani çekirdek "engelliyor + yanlış iddia" derken 11+ sorunda en zararsız görünüyordu.
 */
function invalid(data: Record<string, unknown> = {}): DeliveryEvidence {
  return {kind: "invalid", verified: null, blocking: true, falseClaim: data.yanlis_iddia === true,
    changed: [], problems: [], changedTotal: null};
}

export function decodeDeliveryEvidence(value: unknown): DeliveryEvidence | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "object" || Array.isArray(value)) return invalid();
  const data = value as Record<string, unknown>;
  if (data.schema_version !== undefined && data.schema_version !== 1) return unsupported();
  if ((data.dogrulandi !== null && typeof data.dogrulandi !== "boolean") ||
      typeof data.engelliyor !== "boolean" || typeof data.yanlis_iddia !== "boolean" ||
      !Array.isArray(data.degisen) ||
      !data.degisen.every((path): path is string => typeof path === "string") ||
      !Array.isArray(data.sorunlar) ||
      !data.sorunlar.every((problem): problem is string => typeof problem === "string")) {
    return invalid(data);
  }
  for (const key of ["uyarilar", "kontroller", "olculmeyen", "oneriler", "degisiklik_ozeti"]) {
    if (data[key] !== undefined && !isTextList(data[key])) return invalid(data);
  }
  if (data.ayrintilar_kisaltildi !== undefined && typeof data.ayrintilar_kisaltildi !== "boolean") return invalid(data);
  const hasTamperMetadata = data.supheli_test_degisikligi !== undefined;
  let suspiciousTests = false;
  if (hasTamperMetadata) {
    const value = data.supheli_test_degisikligi;
    if (!value || typeof value !== "object" || Array.isArray(value)) return invalid(data);
    const tamper = value as Record<string, unknown>;
    if (!isCount(tamper.adet) || !isCount(tamper.zayiflatan) || tamper.zayiflatan > tamper.adet ||
        (tamper.turler !== undefined && !isTextList(tamper.turler)) ||
        (tamper.yollar !== undefined && !isTextList(tamper.yollar))) return invalid(data);
    if (tamper.zayiflatan > 0 && data.dogrulandi === true) return invalid(data);
    suspiciousTests = tamper.adet > 0;
  }
  const problemTotal = data.sorun_sayisi;
  const criteriaTotal = data.criteria_count;
  if (problemTotal !== undefined && (!isCount(problemTotal) || problemTotal < data.sorunlar.length)) return invalid(data);
  if (criteriaTotal !== undefined && !isCount(criteriaTotal)) return invalid(data);
  let observedFailed = false;
  let observedUnverified = false;
  let retainedCriteria = 0;
  if (data.criteria !== undefined) {
    if (!Array.isArray(data.criteria)) return invalid(data);
    retainedCriteria = data.criteria.length;
    for (const criterion of data.criteria) {
      if (!criterion || typeof criterion !== "object" || Array.isArray(criterion) ||
          !["passed", "failed", "unverified"].includes(criterion.status)) return invalid(data);
      observedFailed ||= criterion.status === "failed";
      observedUnverified ||= criterion.status === "unverified";
    }
  }
  if (typeof criteriaTotal === "number" && criteriaTotal < retainedCriteria) return invalid(data);
  let statusCounts: DeliveryEvidence["criteriaStatusCounts"];
  if (data.criteria_status_counts !== undefined) {
    const counts = data.criteria_status_counts;
    if (!counts || typeof counts !== "object" || Array.isArray(counts)) return invalid(data);
    const record = counts as Record<string, unknown>;
    if (!isCount(record.passed) || !isCount(record.failed) || !isCount(record.unverified)) return invalid(data);
    statusCounts = {passed: record.passed, failed: record.failed, unverified: record.unverified};
    if (!Number.isSafeInteger(statusCounts.passed + statusCounts.failed + statusCounts.unverified)) return invalid(data);
    if (typeof criteriaTotal === "number" &&
        statusCounts.passed + statusCounts.failed + statusCounts.unverified > criteriaTotal) return invalid(data);
  }
  const total = data.degisen_sayisi;
  if (data.schema_version === 1 && (typeof total !== "number" || !Number.isSafeInteger(total) || total < data.degisen.length)) {
    return invalid(data);
  }
  let truncated = data.ayrintilar_kisaltildi === true;
  const textList = (value: string[], cap: number): string[] => {
    truncated ||= value.length > cap;
    return value.slice(0, cap).map(text => {
      truncated ||= Array.from(text).length > MAX_TEXT;
      return publicText(text);
    });
  };
  const detail = (key: string, cap = MAX_PROBLEMS): string[] | undefined =>
    isTextList(data[key]) ? textList(data[key], cap) : undefined;
  truncated ||= data.degisen.length > MAX_PATHS;
  const paths = data.degisen.slice(0, MAX_PATHS).filter(path => {
    if (sirlariMaskele(path) === path) return true;
    truncated = true;
    return false;
  });
  const result: DeliveryEvidence = {kind: data.schema_version === 1 ? "supported" : "legacy",
    verified: data.dogrulandi, blocking: data.engelliyor, falseClaim: data.yanlis_iddia,
    changed: paths, problems: textList(data.sorunlar, MAX_PROBLEMS),
    deliveryKind: data.teslim_turu === "observation" ? "observation" :
      data.teslim_turu === "artifact" ? "artifact" : "code",
    warnings: detail("uyarilar") ?? [], checks: detail("kontroller"), unmeasured: detail("olculmeyen"),
    advisories: detail("oneriler"), changeSummary: detail("degisiklik_ozeti", MAX_SUMMARY),
    changedTotal: typeof total === "number" ? total : null};
  if (isCount(problemTotal)) result.problemTotal = problemTotal;
  if (isCount(criteriaTotal)) result.criteriaTotal = criteriaTotal;
  if (statusCounts) result.criteriaStatusCounts = statusCounts;
  const representedCriteria = statusCounts
    ? statusCounts.passed + statusCounts.failed + statusCounts.unverified : retainedCriteria;
  // Kritik toplamlar, ayrıntı listeleri kesilmiş veya hiç gönderilmemiş olsa da geçerlidir.
  if (data.sorunlar.length || (result.problemTotal ?? 0) > 0 || observedFailed || (statusCounts?.failed ?? 0) > 0) {
    result.verified = false;
    result.blocking = true;
  } else if (result.verified === true && (suspiciousTests || observedUnverified || (statusCounts?.unverified ?? 0) > 0 ||
      (result.criteriaTotal ?? 0) > representedCriteria)) {
    result.verified = null;
  }
  const rawWarnings = isTextList(data.uyarilar) ? data.uyarilar : [];
  const warningsPreserved = rawWarnings.length <= MAX_PROBLEMS &&
    result.warnings?.length === rawWarnings.length && rawWarnings.every((text, index) =>
      Array.from(text).length <= MAX_TEXT && result.warnings?.[index] === sirlariMaskele(text));
  truncated ||= !warningsPreserved;
  if (truncated || data.ayrintilar_kisaltildi !== undefined) result.detailsTruncated = truncated;
  if (data.sunum === "document" && result.kind === "supported" && result.verified === true &&
      !result.blocking && !result.falseClaim && !hasTamperMetadata && !result.problems.length && result.changed.length === 1 &&
      result.changedTotal === 1 && /\.(?:html?|md|txt|rst)$/i.test(result.changed[0]) &&
      warningsPreserved && !result.unmeasured?.length) result.presentation = "document";
  // Ek ayrıntıların bütçesi kritik sorun/uyarı/ölçüm kaybını silemez.
  if (byteLength(result) > MAX_BYTES) {
    result.detailsTruncated = true;
    for (const key of ["changeSummary", "advisories", "checks", "changed"] as const) {
      const entries = result[key];
      while (entries?.length && byteLength(result) > MAX_BYTES) entries.pop();
    }
    if (byteLength(result) > MAX_BYTES) return invalid(data);
  }
  if (result.changed.length !== 1) result.presentation = undefined;
  return result;
}
