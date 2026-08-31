import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionBridge, PermissionKind, PermissionState } from "./types";
import { EXPLANATION_SEEN_KEY, usePermissions } from "./usePermissions";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function fakeBridge(state: PermissionState = "unknown"): PermissionBridge & {
  request: ReturnType<typeof vi.fn>;
  openSettings: ReturnType<typeof vi.fn>;
} {
  return {
    request: vi.fn().mockResolvedValue(state),
    openSettings: vi.fn().mockResolvedValue(undefined),
  };
}

describe("usePermissions", () => {
  it("kurulurken işletim sisteminden izin istemez", () => {
    const bridge = fakeBridge();

    renderHook(() => usePermissions(bridge));

    expect(bridge.request).not.toHaveBeenCalled();
  });

  it("her özellik için yalnız bir ilk-kullanım açıklaması açar", async () => {
    const bridge = fakeBridge("granted");
    const { result } = renderHook(() => usePermissions(bridge));

    let first: Promise<boolean> | undefined;
    let second: Promise<boolean> | undefined;
    act(() => {
      first = result.current.ensure("microphone");
      second = result.current.ensure("microphone");
    });

    expect(result.current.activeKind).toBe("microphone");
    expect(result.current.phase).toBe("preflight");
    expect(bridge.request).not.toHaveBeenCalled();

    await act(async () => result.current.continue());

    await expect(first).resolves.toBe(true);
    await expect(second).resolves.toBe(true);
    expect(bridge.request).toHaveBeenCalledTimes(1);
    expect(bridge.request).toHaveBeenCalledWith("microphone");
  });

  it("reddedilen izni görünür tutar ve yalnız açıklamanın görüldüğünü saklar", async () => {
    const bridge = fakeBridge("denied");
    const { result } = renderHook(() => usePermissions(bridge));

    let ensured: Promise<boolean> | undefined;
    act(() => { ensured = result.current.ensure("speech"); });
    await act(async () => result.current.continue());

    await expect(ensured).resolves.toBe(false);
    await waitFor(() => expect(result.current.state.speech).toBe("denied"));
    expect(result.current.activeKind).toBe("speech");
    expect(result.current.phase).toBe("denied");
    expect(localStorage.getItem(EXPLANATION_SEEN_KEY)).toBe('{"speech":true}');
    expect(localStorage.getItem("fusion.permissions.speech")).toBeNull();
  });

  it("verilen bir izin için sonraki ensure çağrısında iletişim kutusu veya istek açmaz", async () => {
    const bridge = fakeBridge("granted");
    const { result } = renderHook(() => usePermissions(bridge));

    let first: Promise<boolean> | undefined;
    act(() => { first = result.current.ensure("keychain"); });
    await act(async () => result.current.continue());
    await expect(first).resolves.toBe(true);

    await expect(result.current.ensure("keychain")).resolves.toBe(true);
    expect(result.current.activeKind).toBeNull();
    expect(bridge.request).toHaveBeenCalledTimes(1);
  });

  it("kullanıcı istediğinde yeniden dener ve Sistem Ayarları'nı açar", async () => {
    const bridge = fakeBridge("denied");
    const { result } = renderHook(() => usePermissions(bridge));

    let ensured: Promise<boolean> | undefined;
    act(() => { ensured = result.current.ensure("workspace"); });
    await act(async () => result.current.continue());
    await expect(ensured).resolves.toBe(false);

    bridge.request.mockResolvedValueOnce("granted");
    await act(async () => result.current.retry());
    await act(async () => result.current.openSettings("workspace"));

    expect(result.current.state.workspace).toBe("granted");
    expect(result.current.activeKind).toBeNull();
    expect(bridge.request).toHaveBeenCalledTimes(2);
    expect(bridge.openSettings).toHaveBeenCalledWith("workspace");
  });
});
