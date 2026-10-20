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
  it("aynı izin isteğini çift tıklamada yalnız bir kez çalıştırır ve kuyruğu atlamaz", async () => {
    let release!: (state: PermissionState) => void;
    const bridge = fakeBridge();
    bridge.request.mockImplementationOnce(() => new Promise<PermissionState>((resolve) => { release = resolve; }));
    const { result } = renderHook(() => usePermissions(bridge));
    let microphone: Promise<boolean> | undefined;
    let speech: Promise<boolean> | undefined;

    act(() => {
      microphone = result.current.ensure("microphone");
      speech = result.current.ensure("speech");
    });
    let first!: Promise<void>;
    let duplicate!: Promise<void>;
    act(() => {
      first = result.current.continue();
      duplicate = result.current.continue();
    });

    expect(result.current.isRequesting).toBe(true);
    expect(bridge.request).toHaveBeenCalledTimes(1);
    await act(async () => release("granted"));
    await Promise.all([first, duplicate]);
    await expect(microphone).resolves.toBe(true);
    expect(result.current.activeKind).toBe("speech");
    expect(result.current.phase).toBe("preflight");
    expect(result.current.isRequesting).toBe(false);

    act(() => result.current.dismiss());
    await expect(speech).resolves.toBe(false);
  });

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

  it("farklı özelliklerin eşzamanlı ensure çağrılarını sırayla tamamlar", async () => {
    const bridge = fakeBridge("granted");
    const { result } = renderHook(() => usePermissions(bridge));
    let workspace: Promise<boolean> | undefined;
    let microphone: Promise<boolean> | undefined;

    act(() => {
      workspace = result.current.ensure("workspace");
      microphone = result.current.ensure("microphone");
    });
    expect(result.current.activeKind).toBe("workspace");

    await act(async () => result.current.continue());
    await expect(workspace).resolves.toBe(true);
    expect(result.current.activeKind).toBe("microphone");
    expect(result.current.phase).toBe("preflight");

    await act(async () => result.current.continue());
    await expect(microphone).resolves.toBe(true);
    expect(bridge.request).toHaveBeenNthCalledWith(1, "workspace");
    expect(bridge.request).toHaveBeenNthCalledWith(2, "microphone");
  });

  it.each(["denied", "restricted"] as const)("kuyruktaki sonraki izni, %s sonucu görünür kaldıktan sonra açıkça ilerletir", async (firstResult) => {
    const bridge = fakeBridge();
    bridge.request.mockResolvedValueOnce(firstResult).mockResolvedValueOnce("granted");
    const { result } = renderHook(() => usePermissions(bridge));
    let workspace: Promise<boolean> | undefined;
    let microphone: Promise<boolean> | undefined;

    act(() => {
      workspace = result.current.ensure("workspace");
      microphone = result.current.ensure("microphone");
    });
    await act(async () => result.current.continue());

    expect(result.current.activeKind).toBe("workspace");
    expect(result.current.phase).toBe(firstResult);
    expect(bridge.request).toHaveBeenCalledTimes(1);

    act(() => result.current.continueToNext());
    await expect(workspace).resolves.toBe(false);
    expect(result.current.activeKind).toBe("microphone");
    expect(result.current.phase).toBe("preflight");

    await act(async () => result.current.continue());
    await expect(microphone).resolves.toBe(true);
  });

  it("saklanmış açıklamadan sonra native gerçeği sorgular, ret varsaymaz", async () => {
    localStorage.setItem(EXPLANATION_SEEN_KEY, '{"speech":true}');
    const bridge = fakeBridge("granted");
    const { result } = renderHook(() => usePermissions(bridge));
    let ensured: Promise<boolean> | undefined;

    act(() => { ensured = result.current.ensure("speech"); });

    expect(result.current.state.speech).toBe("unknown");
    await waitFor(() => expect(bridge.request).toHaveBeenCalledWith("speech"));
    await expect(ensured).resolves.toBe(true);
    await waitFor(() => expect(result.current.state.speech).toBe("granted"));
  });

  it("reddedilen izni görünür tutar ve yalnız açıklamanın görüldüğünü saklar", async () => {
    const bridge = fakeBridge("denied");
    const { result } = renderHook(() => usePermissions(bridge));

    let ensured: Promise<boolean> | undefined;
    act(() => { ensured = result.current.ensure("speech"); });
    await act(async () => result.current.continue());

    await waitFor(() => expect(result.current.state.speech).toBe("denied"));
    expect(result.current.activeKind).toBe("speech");
    expect(result.current.phase).toBe("denied");
    expect(localStorage.getItem(EXPLANATION_SEEN_KEY)).toBe('{"speech":true}');
    expect(localStorage.getItem("fusion.permissions.speech")).toBeNull();
    act(() => result.current.dismiss());
    await expect(ensured).resolves.toBe(false);
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

    bridge.request.mockResolvedValueOnce("granted");
    await act(async () => result.current.retry());
    await expect(ensured).resolves.toBe(true);
    await act(async () => result.current.openSettings("workspace"));

    expect(result.current.state.workspace).toBe("granted");
    expect(result.current.activeKind).toBeNull();
    expect(bridge.request).toHaveBeenCalledTimes(2);
    expect(bridge.openSettings).toHaveBeenCalledWith("workspace");
  });

  it("köprü isteği hata verdiğinde güvenli hata gösterir ve retry özgün bekleyeni tamamlar", async () => {
    const bridge = fakeBridge();
    bridge.request.mockRejectedValueOnce(new Error("secret-token TCC kullanılamıyor"));
    bridge.request.mockResolvedValueOnce("granted");
    const { result } = renderHook(() => usePermissions(bridge));
    let ensured: Promise<boolean> | undefined;
    let settled = false;

    act(() => { ensured = result.current.ensure("keychain"); });
    void ensured!.finally(() => { settled = true; });
    await expect(act(async () => result.current.continue())).resolves.toBeUndefined();

    await Promise.resolve();
    expect(settled).toBe(false);
    expect(result.current.state.keychain).toBe("unknown");
    expect(result.current.activeKind).toBe("keychain");
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/yeniden deneyin/i);
    expect(result.current.error).not.toContain("secret-token");

    await act(async () => result.current.retry());
    await expect(ensured).resolves.toBe(true);
  });

  it("Sistem Ayarları açılamazsa reddi yutmak yerine eyleme dönük güvenli hata gösterir", async () => {
    const bridge = fakeBridge("denied");
    bridge.openSettings.mockRejectedValueOnce(new Error("/Users/private secret-token"));
    const { result } = renderHook(() => usePermissions(bridge));

    act(() => { void result.current.ensure("microphone"); });
    await act(async () => result.current.continue());
    await expect(act(async () => result.current.openSettings("microphone"))).resolves.toBeUndefined();

    expect(result.current.error).toMatch(/elle açıp yeniden deneyin/i);
    expect(result.current.error).not.toContain("secret-token");
  });

  it("Şimdi değil özgün bekleyeni false tamamlar ve kuyruktaki izne ilerler", async () => {
    const bridge = fakeBridge("denied");
    const { result } = renderHook(() => usePermissions(bridge));
    let workspace: Promise<boolean> | undefined;
    let microphone: Promise<boolean> | undefined;

    act(() => {
      workspace = result.current.ensure("workspace");
      microphone = result.current.ensure("microphone");
    });
    await act(async () => result.current.continue());
    act(() => result.current.dismiss());

    await expect(workspace).resolves.toBe(false);
    expect(result.current.activeKind).toBe("microphone");
    act(() => result.current.dismiss());
    await expect(microphone).resolves.toBe(false);
    expect(result.current.activeKind).toBeNull();
  });
});
