/** Runtime kanıt özetini doğrular; model metni doğrulama kaynağı değildir. */
export interface DeliveryEvidence {
  kind: "supported" | "legacy" | "unsupported" | "invalid";
  verified: boolean | null;
  blocking: boolean;
  falseClaim: boolean;
  changed: string[];
  problems: string[];
  changedTotal: number | null;
}

function unknown(kind: "unsupported" | "invalid"): DeliveryEvidence {
  return {kind, verified: null, blocking: false, falseClaim: false,
    changed: [], problems: [], changedTotal: null};
}

export function decodeDeliveryEvidence(value: unknown): DeliveryEvidence | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "object" || Array.isArray(value)) return unknown("invalid");
  const data = value as Record<string, unknown>;
  if (data.schema_version !== undefined && data.schema_version !== 1) return unknown("unsupported");
  if ((data.dogrulandi !== null && typeof data.dogrulandi !== "boolean") ||
      typeof data.engelliyor !== "boolean" || typeof data.yanlis_iddia !== "boolean" ||
      !Array.isArray(data.degisen) || data.degisen.length > 50 ||
      !data.degisen.every((path): path is string => typeof path === "string") ||
      !Array.isArray(data.sorunlar) || data.sorunlar.length > 10 ||
      !data.sorunlar.every((problem): problem is string => typeof problem === "string")) {
    return unknown("invalid");
  }
  const total = data.degisen_sayisi;
  if (data.schema_version === 1 && (typeof total !== "number" || !Number.isSafeInteger(total) || total < data.degisen.length)) {
    return unknown("invalid");
  }
  return {kind: data.schema_version === 1 ? "supported" : "legacy",
    verified: data.dogrulandi, blocking: data.engelliyor, falseClaim: data.yanlis_iddia,
    changed: [...data.degisen], problems: [...data.sorunlar],
    changedTotal: typeof total === "number" ? total : null};
}
