import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ check: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true }));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));

import { useUpdateAvailable, YENIDEN_KONTROL_MS } from "./useUpdateAvailable";

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers(); });

// Ölçüldü (30 Ekim): kontrol yalnız açılışta bir kez yapılıyor, uzun açık kalan uygulama yeni sürümü görmüyordu (U5-44).
it("açılışta ve her yeniden kontrol aralığında güncelleme sorar", async () => {
  vi.useFakeTimers();
  mocks.check.mockResolvedValue(null);
  renderHook(() => useUpdateAvailable());
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(mocks.check).toHaveBeenCalledTimes(1);
  mocks.check.mockResolvedValue({ version: "2.0.0", close: vi.fn().mockResolvedValue(undefined) });
  await act(async () => { await vi.advanceTimersByTimeAsync(YENIDEN_KONTROL_MS); });
  expect(mocks.check).toHaveBeenCalledTimes(2);
});
