import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NABIZ_ARALIGI_MS, useKapatmaNabzi } from "./closeHeartbeat";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

/* Ölçüldü (30 Ekim): kapatma sorusu açıkken Rust arayüzün canlı olup olmadığını bilemiyordu;
   yanıtsız arayüzde kapanış sonsuza dek bekliyordu (R2-14). Soru açıkken saniyede bir nabız gider. */
describe("useKapatmaNabzi", () => {
  it("soru açıldığında hemen, sonra her aralıkta nabız yollar", () => {
    const gonder = vi.fn(async () => undefined);
    renderHook(() => useKapatmaNabzi(true, gonder));
    expect(gonder).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(NABIZ_ARALIGI_MS * 3); });
    expect(gonder).toHaveBeenCalledTimes(4);
  });

  it("soru kapanınca nabız durur", () => {
    const gonder = vi.fn(async () => undefined);
    const { rerender } = renderHook(({ acik }) => useKapatmaNabzi(acik, gonder), { initialProps: { acik: true } });
    rerender({ acik: false });
    gonder.mockClear();
    act(() => { vi.advanceTimersByTime(NABIZ_ARALIGI_MS * 5); });
    expect(gonder).not.toHaveBeenCalled();
  });

  it("soru hiç açılmadıysa nabız yollamaz", () => {
    const gonder = vi.fn(async () => undefined);
    renderHook(() => useKapatmaNabzi(false, gonder));
    act(() => { vi.advanceTimersByTime(NABIZ_ARALIGI_MS * 5); });
    expect(gonder).not.toHaveBeenCalled();
  });

  it("gönderim hatası işlenmemiş reddetmeye dönüşmez", async () => {
    const gonder = vi.fn(async () => { throw new Error("ipc yok"); });
    renderHook(() => useKapatmaNabzi(true, gonder));
    await act(async () => { await Promise.resolve(); });
    expect(gonder).toHaveBeenCalled();
  });
});
