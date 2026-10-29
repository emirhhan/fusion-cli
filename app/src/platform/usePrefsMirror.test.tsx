import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePrefsMirror } from "./usePrefsMirror";

function istemci() {
  return {
    request: vi.fn(async (name: string) => name === "ayar.arayuz" ? { ok: true, degerler: {} } : { ok: true }),
  };
}
afterEach(() => localStorage.clear());

describe("usePrefsMirror", () => {
  it("başka sohbete geçince yedekleme durmaz; yazma güncel istemciye gider", async () => {
    const a = istemci();
    const b = istemci();
    const { rerender, unmount } = renderHook(({ c }) => usePrefsMirror(c), { initialProps: { c: a } });
    await waitFor(() => expect(a.request).toHaveBeenCalledWith("ayar.arayuz", {}));
    rerender({ c: b });
    await new Promise((cozumle) => setTimeout(cozumle, 10));
    localStorage.setItem("fusion.theme", "light");
    expect(b.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.theme", deger: "light" });
    expect(a.request).not.toHaveBeenCalledWith("ayar.arayuz_kaydet", expect.anything());
    unmount();
    const once = b.request.mock.calls.length;
    localStorage.setItem("fusion.theme", "dark");
    expect(b.request.mock.calls.length).toBe(once);
  });

  it("oturum kalmadığında yazma TypeError değil kontrollü hata verir", async () => {
    const a = istemci();
    const { rerender } = renderHook(({ c }) => usePrefsMirror(c), { initialProps: { c: a as ReturnType<typeof istemci> | undefined } });
    await waitFor(() => expect(a.request).toHaveBeenCalledWith("ayar.arayuz", {}));
    await new Promise((cozumle) => setTimeout(cozumle, 10));
    rerender({ c: undefined });
    const hata = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => localStorage.setItem("fusion.theme", "light")).not.toThrow();
    await vi.waitFor(() => expect(hata).toHaveBeenCalledWith("Tercih kaydedilemedi: Error: Fusion oturumu yok."));
    hata.mockRestore();
  });
});
