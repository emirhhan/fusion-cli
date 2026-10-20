import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  RuntimeBackendStatus,
  RuntimeProgress,
  RuntimeTransport,
} from "./types";
import { useRuntime } from "./useRuntime";

afterEach(cleanup);

function fakeRuntimeTransport(
  initial: RuntimeBackendStatus,
  prepared: RuntimeBackendStatus,
): RuntimeTransport & { prepare: ReturnType<typeof vi.fn> } {
  return {
    status: vi.fn().mockResolvedValue(initial),
    prepare: vi.fn().mockResolvedValue(prepared),
    repair: vi.fn().mockResolvedValue(prepared),
    listenProgress: vi.fn().mockResolvedValue(() => undefined),
  };
}

function failingRuntimeTransport(message: string): RuntimeTransport {
  return {
    status: vi.fn().mockResolvedValue({
      state: "eksik",
      message: "Kurulum gerekli",
      can_repair: false,
    }),
    prepare: vi.fn().mockRejectedValue(new Error(message)),
    repair: vi.fn().mockRejectedValue(new Error(message)),
    listenProgress: vi.fn().mockResolvedValue(() => undefined),
  };
}

describe("useRuntime", () => {
  it("hazır değilse prepare çalıştırıp hazır duruma geçer", async () => {
    const transport = fakeRuntimeTransport(
      { state: "eksik", message: "Kurulum gerekli", can_repair: false },
      { state: "hazir", version: "0.3.0a1", message: "Hazır", can_repair: false },
    );

    const { result } = renderHook(() => useRuntime(transport));

    await waitFor(() => expect(result.current.state).toBe("hazir"));
    expect(transport.prepare).toHaveBeenCalledOnce();
    expect(result.current.version).toBe("0.3.0a1");
  });

  it("kurulum hatasını onarılabilir durumda tutar", async () => {
    const transport = failingRuntimeTransport("Arşiv özeti uyuşmuyor");

    const { result } = renderHook(() => useRuntime(transport));

    await waitFor(() => expect(result.current.state).toBe("onarilabilir"));
    expect(result.current.message).toContain("Arşiv özeti uyuşmuyor");
  });

  it("ilerleme olayını güvenli bir yüzdeye dönüştürür", async () => {
    let onProgress: ((progress: RuntimeProgress) => void) | undefined;
    const transport = fakeRuntimeTransport(
      { state: "eksik", message: "Kurulum gerekli", can_repair: false },
      { state: "hazir", message: "Hazır", can_repair: false },
    );
    transport.prepare = vi.fn(() => new Promise<RuntimeBackendStatus>(() => undefined));
    transport.listenProgress = vi.fn(async (listener) => {
      onProgress = listener;
      return () => undefined;
    });

    const { result } = renderHook(() => useRuntime(transport));
    await waitFor(() => expect(result.current.state).toBe("kuruluyor"));
    onProgress?.({ stage: "extract", completed: 7, total: 10, message: "Dosyalar açılıyor" });

    await waitFor(() => expect(result.current.progress).toBe(70));
    expect(result.current.message).toBe("Dosyalar açılıyor");
  });
});
