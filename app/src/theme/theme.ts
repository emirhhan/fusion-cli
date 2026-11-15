export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "fusion.theme";

const isThemePreference = (value: string | null): value is ThemePreference =>
  value === "system" || value === "light" || value === "dark";

/**
 * Varsayılan parametre (`= localStorage`) `try`'dan ÖNCE değerlendirilirdi: depoya erişim
 * SecurityError atarsa `main.tsx` modül yüklemesinde patlar ve pencere boş açılırdı (U6-10).
 * Depo artık `try` içinde çözülür.
 */
export function readThemePreference(storage?: Pick<Storage, "getItem">): ThemePreference {
  try {
    const value = (storage ?? localStorage).getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : "dark";
  } catch {
    return "dark";
  }
}

export function saveThemePreference(
  preference: ThemePreference,
  storage?: Pick<Storage, "setItem">,
): void {
  try {
    (storage ?? localStorage).setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Tema tercihi kalıcılaştırılamasa da uygulama kullanılabilir kalır.
  }
}

export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  return preference === "system" ? (prefersDark ? "dark" : "light") : preference;
}

export function applyTheme(
  preference: ThemePreference,
  root: HTMLElement = document.documentElement,
  prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
): ResolvedTheme {
  const resolved = resolveTheme(preference, prefersDark);
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  return resolved;
}
