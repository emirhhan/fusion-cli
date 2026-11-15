import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useKitsPrewarm } from "./useKitsPrewarm";

afterEach(cleanup);

describe("useKitsPrewarm", () => {
  it("çekirdek hazır olmadan Kits'i başlatmaz", () => {
    const start = vi.fn(async () => ({ url: "http://127.0.0.1:50100" }));
    renderHook(() => useKitsPrewarm(false, start));
    expect(start).not.toHaveBeenCalled();
  });

  it("çekirdek hazır olunca bir kez başlatır; oturum düşüp geri gelince tekrarlamaz", () => {
    const start = vi.fn(async () => ({ url: "http://127.0.0.1:50101" }));
    const { rerender } = renderHook(({ ready }) => useKitsPrewarm(ready, start), { initialProps: { ready: true } });
    rerender({ ready: false });
    rerender({ ready: true });
    expect(start).toHaveBeenCalledTimes(1);
  });

  it("ön başlatma hatası yutulmaz, uyarı olarak kaydedilir ve arayüzü düşürmez", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const start = vi.fn(() => Promise.reject(new Error("Node.js 24 veya üzeri bulunamadı.")));
    renderHook(() => useKitsPrewarm(true, start));
    await vi.waitFor(() => expect(warn).toHaveBeenCalledWith(expect.stringContaining("Kits ön başlatması"), expect.any(Error)));
    warn.mockRestore();
  });
});
