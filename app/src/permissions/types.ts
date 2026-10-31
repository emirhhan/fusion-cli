export type PermissionKind =
  | "workspace"
  | "microphone"
  | "speech"
  | "keychain"
  | "accessibility"
  | "screenRecording";

/** Sistem Ayarları'nda doğrudan bölümü olan izinler (`izin_ayarlari_ac` bağlantısı var). */
const SETTINGS_LINKED: ReadonlySet<PermissionKind> = new Set<PermissionKind>([
  "microphone",
  "speech",
  "accessibility",
  "screenRecording",
]);

export function hasSettingsLink(kind: PermissionKind | null): boolean {
  return kind !== null && SETTINGS_LINKED.has(kind);
}

/** Çekirdeğin `izin_gerekli` / `MasaustuIzinGerekli` türü → arayüz izin türü. */
export function desktopPermissionKind(value: unknown): PermissionKind | null {
  if (value === "accessibility") return "accessibility";
  if (value === "screen_recording") return "screenRecording";
  return null;
}

export type PermissionState = "unknown" | "granted" | "denied" | "restricted";

/** Native katman Task 2'de bu sözleşmeyi Tauri komutlarına bağlar. */
export interface PermissionBridge {
  request(kind: PermissionKind): Promise<PermissionState>;
  openSettings(kind: PermissionKind): Promise<void>;
}

export type PermissionPromptPhase = "preflight" | "denied" | "restricted" | "error";
