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
    if (result.ok === true || (result.ok === undefined && allowLegacy)) return { ok: true };
    return { ok: false, message: String(result.message ?? result.metin ?? fallback) };
  }
  return { ok: false, message: fallback };
}
