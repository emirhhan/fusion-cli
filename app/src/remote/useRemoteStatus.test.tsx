import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { markRemoteInUse } from "./remoteFlag";
import { KAPALI, useRemoteStatus } from "./useRemoteStatus";

// Ölçüldü (31 Ekim): başlıkta uzaktan kontrol göstergesi yoktu; `uzak.durum` yalnız Ayarlar'dan okunuyordu.

const client = (over: Record<string, unknown> = {}) =>
  ({
    request: vi.fn(async (name: string) =>
      name === "uzak.bekleyen"
        ? { ok: true, sorular: [{ soruId: "q1" }] }
        : { ok: true, dinliyor: true, cihazSayisi: 2, ...over },
    ),
  }) as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };

beforeEach(() => window.localStorage.clear());

it("uzaktan erişim hiç kurulmamışsa yoklamaz ve kapalı görünür", () => {
  const c = client();
  const { result } = renderHook(() => useRemoteStatus(c));
  expect(c.request).not.toHaveBeenCalled();
  expect(result.current).toEqual(KAPALI);
});

it("kurulmuşsa dinleme, cihaz ve bekleyen onay sayısını okur", async () => {
  markRemoteInUse(true);
  const c = client();
  const { result } = renderHook(() => useRemoteStatus(c));
  await waitFor(() => expect(result.current.known).toBe(true));
  expect(result.current).toEqual({ known: true, listening: true, deviceCount: 2, pendingApprovals: 1 });
  expect(c.request).toHaveBeenCalledWith("uzak.durum", {});
});

it("çekirdek hata verirse sessizce kapalı kalır", async () => {
  markRemoteInUse(true);
  const c = { request: vi.fn(async () => { throw new Error("kopuk"); }) } as unknown as ProtocolClient;
  const { result } = renderHook(() => useRemoteStatus(c));
  await waitFor(() => expect((c.request as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));
  expect(result.current).toEqual(KAPALI);
});

it("oturum içinde uzaktan erişim ilk kez kurulunca anahtar yeniden başlatmasız okumaya başlar", async () => {
  // Ölçüldü (31 Ekim): bayrak yalnız effect kurulurken okunuyordu; Ayarlar'da sunucu açılsa da
  // başlık uygulama yeniden başlatılana dek "kapalı" kalıyordu.
  const c = client();
  const { result } = renderHook(() => useRemoteStatus(c));
  expect(result.current).toEqual(KAPALI);
  act(() => markRemoteInUse(true));
  await waitFor(() => expect(result.current.known).toBe(true));
  expect(result.current.deviceCount).toBe(2);
  act(() => markRemoteInUse(false));
  await waitFor(() => expect(result.current).toEqual(KAPALI));
});
