import { invoke } from "@tauri-apps/api/core";
import type { PermissionBridge, PermissionKind, PermissionState } from "../permissions/types";

export interface NativePermissionCapability {
  state: PermissionState;
  supported: boolean;
}

export function queryPermission(kind: PermissionKind): Promise<NativePermissionCapability> {
  return invoke<NativePermissionCapability>("izin_durumu", { kind });
}

export const nativePermissionBridge: PermissionBridge = {
  async request(kind) {
    const capability = await invoke<NativePermissionCapability>("izin_iste", { kind });
    return capability.supported ? capability.state : "restricted";
  },
  openSettings(kind) {
    return invoke<void>("izin_ayarlari_ac", { kind });
  },
};
