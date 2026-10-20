import { readStorage, writeStorage } from "../platform/storage";

export const REMOTE_SCOPES_KEY = "fusion.remote.pairing-scopes.v1";
export const ELEVATED_SCOPES = [
  { id: "project.write", etiket: "Proje dosyalarını değiştirme" },
  { id: "desktop.observe", etiket: "Ekranı görme (telefonda canlı ekran)" },
  { id: "desktop.control", etiket: "Masaüstünü kontrol etme" },
  { id: "production.deploy", etiket: "Üretime yayın" },
];

function validatedScopes(scopes: unknown[]): string[] {
  return [...new Set(scopes.filter((scope): scope is string =>
    typeof scope === "string" && ELEVATED_SCOPES.some((item) => item.id === scope)))];
}

/** Bu tercih yalnız yeni eşleştirmelere aittir; cihaz yetkisi veya sır içermez. */
export function readPairingScopes(): string[] {
  const result = readStorage(() => window.localStorage, REMOTE_SCOPES_KEY);
  if (!result.ok || !result.value) return [];
  try {
    const value: unknown = JSON.parse(result.value);
    if (typeof value !== "object" || value === null || !("version" in value)
      || value.version !== 1 || !("scopes" in value) || !Array.isArray(value.scopes)) return [];
    return validatedScopes(value.scopes);
  } catch { return []; }
}

export function savePairingScopes(scopes: string[]): void {
  writeStorage(() => window.localStorage, REMOTE_SCOPES_KEY,
    JSON.stringify({ version: 1, scopes: validatedScopes(scopes) }));
}
