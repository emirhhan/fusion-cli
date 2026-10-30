import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { invoke, convertFileSrc } = vi.hoisted(() => ({
  invoke: vi.fn(),
  convertFileSrc: vi.fn((yol: string, sema: string) => `${sema}://localhost/${yol}`),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke, convertFileSrc }));

import { ayriKokenliOnizlemeAdresi } from "./htmlPreviewSource";

beforeEach(() => {
  invoke.mockReset();
  convertFileSrc.mockClear();
});
afterEach(() => {
  Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
});

/* Ölçüldü (30 Ekim): srcdoc önizlemesi ana pencerenin CSP'sini miras alıp paketli uygulamada satır
   içi betikleri engelliyordu (U4-47). Kabukta içerik fusion-preview:// şemasından, ayrı kökenle sunulur. */
describe("ayriKokenliOnizlemeAdresi", () => {
  it("kabuk yoksa (tarayıcı/test) null döner; srcdoc yedeği kullanılır", async () => {
    await expect(ayriKokenliOnizlemeAdresi("<p>x</p>")).resolves.toBeNull();
    expect(invoke).not.toHaveBeenCalled();
  });

  it("kabukta içeriği Rust'a bırakır ve fusion-preview adresini döndürür", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    invoke.mockResolvedValue("abc123");

    await expect(ayriKokenliOnizlemeAdresi("<script>1</script>")).resolves.toBe("fusion-preview://localhost/abc123");

    expect(invoke).toHaveBeenCalledWith("onizleme_ayarla", { icerik: "<script>1</script>" });
    expect(convertFileSrc).toHaveBeenCalledWith("abc123", "fusion-preview");
  });

  it("Rust reddederse null döner (srcdoc yedeği)", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    invoke.mockRejectedValue("önizleme 5 MiB sınırını aşıyor");

    await expect(ayriKokenliOnizlemeAdresi("x")).resolves.toBeNull();
  });
});
