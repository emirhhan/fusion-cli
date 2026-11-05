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
  deliveryKind?: "code" | "artifact";
  changedTotal: number | null;
  presentation?: "document";
  checks?: string[];
  unmeasured?: string[];
  advisories?: string[];
  changeSummary?: string[];
  detailsTruncated?: boolean;
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
    deliveryKind: data.teslim_turu === "artifact" ? "artifact" : "code",
    warnings: detail("uyarilar") ?? [], checks: detail("kontroller"), unmeasured: detail("olculmeyen"),
    advisories: detail("oneriler"), changeSummary: detail("degisiklik_ozeti", MAX_SUMMARY),
    changedTotal: typeof total === "number" ? total : null};
  if (truncated || data.ayrintilar_kisaltildi !== undefined) result.detailsTruncated = truncated;
  if (data.sunum === "document" && result.kind === "supported" && result.verified === true &&
      !result.blocking && !result.falseClaim && !result.problems.length && result.changed.length === 1 &&
      result.changedTotal === 1 && /\.(?:html?|md|txt|rst)$/i.test(result.changed[0]) &&
      !result.warnings?.length && !result.unmeasured?.length) result.presentation = "document";
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
