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
}

/** Çekirdeğin `completion_evidence.py` tavanları; aşan liste GEÇERSİZLİK değil, kesilir. */
const MAX_PATHS = 50;
const MAX_PROBLEMS = 10;

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
  if (data.uyarilar !== undefined && (!Array.isArray(data.uyarilar) ||
      !data.uyarilar.every((warning): warning is string => typeof warning === "string"))) return invalid(data);
  const total = data.degisen_sayisi;
  if (data.schema_version === 1 && (typeof total !== "number" || !Number.isSafeInteger(total) || total < data.degisen.length)) {
    return invalid(data);
  }
  return {kind: data.schema_version === 1 ? "supported" : "legacy",
    verified: data.dogrulandi, blocking: data.engelliyor, falseClaim: data.yanlis_iddia,
    changed: data.degisen.slice(0, MAX_PATHS), problems: data.sorunlar.slice(0, MAX_PROBLEMS),
    deliveryKind: data.teslim_turu === "artifact" ? "artifact" : "code",
    warnings: Array.isArray(data.uyarilar) ? data.uyarilar.slice(0, MAX_PROBLEMS) : [],
    changedTotal: typeof total === "number" ? total : null};
}
