export type OperationResult = { ok: true } | { ok: false; message: string };
export type CommandResult = OperationResult;
export function errorMessage(reason: unknown): string {
  if (reason && typeof reason === "object" && "message" in reason && typeof reason.message === "string") return reason.message;
  return String(reason);
}
export function operationResult(value: unknown, fallback: string, allowLegacy = false): OperationResult {
  if (value === undefined && allowLegacy) return { ok: true };
  if (value && typeof value === "object") {
    const result = value as Record<string, unknown>;
    // Eski çekirdek `ok` göndermez; ama `{hata: "…"}` ile hata dönüyorsa bu başarı SAYILMAZ (U5-18).
    const hataAlani = result.hata ?? result.error;
    const eskiBasari = result.ok === undefined && allowLegacy && (hataAlani === undefined || hataAlani === null || hataAlani === "");
    if (result.ok === true || eskiBasari) return { ok: true };
    return { ok: false, message: String(result.message ?? result.metin ?? hataAlani ?? fallback) };
  }
  return { ok: false, message: fallback };
}
