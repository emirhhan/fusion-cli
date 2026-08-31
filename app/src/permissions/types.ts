export type PermissionKind = "workspace" | "microphone" | "speech" | "keychain";

export type PermissionState = "unknown" | "granted" | "denied" | "restricted";

/** Native katman Task 2'de bu sözleşmeyi Tauri komutlarına bağlar. */
export interface PermissionBridge {
  request(kind: PermissionKind): Promise<PermissionState>;
  openSettings(kind: PermissionKind): Promise<void>;
}

export type PermissionPromptPhase = "preflight" | "denied" | "restricted";
