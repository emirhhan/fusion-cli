import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { PreviewPanel, isLocalPreviewUrl } from "./PreviewPanel";

afterEach(cleanup);

const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fusion-preview");
const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

afterEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
});

describe("PreviewPanel", () => {
  it("yalnız localhost geliştirme adreslerini gömer", () => {
    expect(isLocalPreviewUrl("http://localhost:5173/game")).toBe(true);
    expect(isLocalPreviewUrl("http://127.0.0.1:3000")).toBe(true);
    expect(isLocalPreviewUrl("http://[::1]:8080")).toBe(true);
    expect(isLocalPreviewUrl("https://example.com")).toBe(false);
    expect(isLocalPreviewUrl("javascript:alert(1)")).toBe(false);
    expect(isLocalPreviewUrl("http://localhost.evil.example")).toBe(false);
  });

  it("seçili görseli protokolden güvenli veri adresiyle gösterir", async () => {
    const client = {
      request: vi.fn(async () => ({
        ok: true, yol: "assets/hero.png", tur: "image", mime: "image/png",
        boyut: 12, base64: "aGVsbG8=",
      })),
    } as unknown as ProtocolClient;

    render(<PreviewPanel client={client} selectedPath="assets/hero.png" />);

    const image = await screen.findByRole("img", { name: "assets/hero.png önizlemesi" });
    expect(image.getAttribute("src")).toBe("blob:fusion-preview");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(client.request).toHaveBeenCalledWith("proje.onizle", { yol: "assets/hero.png" });
  });

  it("dış URL'yi gömmez ve desteklenmeyen dosyada açık hata gösterir", async () => {
    const client = {
      request: vi.fn(async () => ({
        ok: false, kod: "UNSUPPORTED_PREVIEW",
        metin: "Bu dosya türü uygulama içinde önizlenemiyor.",
      })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath="archive.zip" />);

    expect(await screen.findByText("Bu dosya türü uygulama içinde önizlenemiyor.")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Yerel önizleme adresi" }), {
      target: { value: "https://example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Adresi aç" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("yalnız localhost"));
    expect(screen.queryByTitle("Yerel geliştirme önizlemesi")).toBeNull();
  });
});
