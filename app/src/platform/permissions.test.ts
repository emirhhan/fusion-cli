import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import {
  nativePermissionBridge,
  queryPermission,
  type NativePermissionCapability,
} from "./permissions";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

describe("native permission bridge", () => {
  beforeEach(() => vi.mocked(invoke).mockReset());

  it("queries status without requesting permission and preserves capability support", async () => {
    const capability: NativePermissionCapability = { state: "denied", supported: true };
    vi.mocked(invoke).mockResolvedValue(capability);

    await expect(queryPermission("microphone")).resolves.toEqual(capability);
    expect(invoke).toHaveBeenCalledWith("izin_durumu", { kind: "microphone" });
  });

  it("requests the exact native permission kind", async () => {
    vi.mocked(invoke).mockResolvedValue({ state: "granted", supported: true });

    await expect(nativePermissionBridge.request("speech")).resolves.toBe("granted");
    expect(invoke).toHaveBeenCalledWith("izin_iste", { kind: "speech" });
  });

  it("does not treat an unsupported capability as granted", async () => {
    vi.mocked(invoke).mockResolvedValue({ state: "granted", supported: false });

    await expect(nativePermissionBridge.request("keychain")).resolves.toBe("restricted");
  });

  it("opens only the requested capability settings", async () => {
    vi.mocked(invoke).mockResolvedValue(undefined);

    await nativePermissionBridge.openSettings("workspace");
    expect(invoke).toHaveBeenCalledWith("izin_ayarlari_ac", { kind: "workspace" });
  });
});
