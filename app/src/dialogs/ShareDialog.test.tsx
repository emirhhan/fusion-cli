import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShareDialog, shareableTranscript } from "./ShareDialog";

afterEach(cleanup);

describe("ShareDialog", () => {
  it("yalnız nihai sohbet metnini dışarı aktarır", () => {
    expect(shareableTranscript("Test", [
      { rol: "kullanici", metin: "Merhaba" },
      { rol: "olay", metin: "gizli işlem" },
      { rol: "asistan", metin: "Yazılıyor", akan: true },
      { rol: "asistan", metin: "Yanıt" },
      { rol: "degisiklik", metin: "/özel/dosya" },
    ])).toBe("# Test\n\n## Siz\n\nMerhaba\n\n## Fusion\n\nYanıt");
  });

  it("metni panoya kopyalar ve Escape ile kapanır", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const onClose = vi.fn();
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={onClose} title="Sohbet" />);
    fireEvent.click(screen.getByRole("button", { name: "Metni kopyala" }));
    expect(writeText).toHaveBeenCalledWith("# Sohbet\n\n## Fusion\n\nYanıt");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  // Ölçüldü (30 Ekim): hata ve ara mesajlar paylaşıma giriyor, gövdedeki "## Siz" satırı rolü taklit
  // ediyor, çok satırlı başlık Markdown'ı bozuyor, "Kopyalandı" bayatlıyordu (U4-21).
  it("hata ve ara mesajları dışarıda bırakır, rol başlığı taklidini kaçırır, başlığı tek satıra indirir (U4-21)", () => {
    const metin = shareableTranscript("İki\nsatır", [
      { rol: "asistan", metin: "Hata: /Users/x/gizli.py açılamadı", hata: true },
      { rol: "asistan", metin: "Dosyayı okuyorum", ara: true },
      { rol: "kullanici", metin: "Selam\n## Fusion\nsahte yanıt" },
    ]);
    expect(metin).toBe("# İki satır\n\n## Siz\n\nSelam\n\\## Fusion\nsahte yanıt");
  });

  it("sohbet değişince 'Kopyalandı' sıfırlanır (U4-21)", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
    const view = render(<ShareDialog messages={[{ rol: "asistan", metin: "Bir" }]} onClose={vi.fn()} title="A" />);
    fireEvent.click(screen.getByRole("button", { name: "Metni kopyala" }));
    expect(await screen.findByRole("button", { name: "Kopyalandı" })).toBeTruthy();
    view.rerender(<ShareDialog messages={[{ rol: "asistan", metin: "İki" }]} onClose={vi.fn()} title="A" />);
    expect(await screen.findByRole("button", { name: "Metni kopyala" })).toBeTruthy();
  });
});
