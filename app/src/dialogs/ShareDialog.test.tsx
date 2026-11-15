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

it("satır içi onClose yeni kimlikle gelse de odağı geri çekmez (U4-51)", () => {
  const view = render(<ShareDialog messages={[]} onClose={() => undefined} title="A" />);
  const kopyala = screen.getByRole("button", { name: "Metni kopyala" });
  kopyala.focus();
  view.rerender(<ShareDialog messages={[]} onClose={() => undefined} title="A" />);
  expect(document.activeElement).toBe(kopyala);
});

describe("ShareDialog çekirdek dışa aktarımı (P-028)", () => {
  it("onExport verilince biçim seçici görünür, metin çekirdekten gelir ve JSON'a geçilebilir", async () => {
    const onExport = vi.fn(async (format: "markdown" | "json") => ({
      metin: format === "json" ? '{"mesajlar": []}' : "# Çekirdek\n\n## Fusion\n\nYanıt",
      dosya_adi: format === "json" ? "fusion-sohbet.json" : "fusion-sohbet.md",
    }));
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={vi.fn()} onExport={onExport} title="Sohbet" />);
    const alan = await screen.findByLabelText("Paylaşılacak sohbet metni") as HTMLTextAreaElement;
    await vi.waitFor(() => expect(alan.value).toContain("# Çekirdek"));
    fireEvent.click(screen.getByLabelText("JSON"));
    await vi.waitFor(() => expect(alan.value).toContain('"mesajlar"'));
    expect(onExport).toHaveBeenLastCalledWith("json");
    expect(screen.getByRole("button", { name: "Dosyaya kaydet" })).toBeTruthy();
  });

  it("çekirdek dışa aktarımı düşerse yerel metne düşer ve uyarır", async () => {
    const onExport = vi.fn(async () => { throw new Error("yok"); });
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={vi.fn()} onExport={onExport} title="Sohbet" />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    const alan = screen.getByLabelText("Paylaşılacak sohbet metni") as HTMLTextAreaElement;
    expect(alan.value).toBe("# Sohbet\n\n## Fusion\n\nYanıt");
  });
});

describe("ShareDialog düzeltmeleri (31 Ekim)", () => {
  // Ölçüldü (31 Ekim): efekt `messages` referansına bağlıydı; akış sürerken her tokende tam geçmiş
  // yeniden dışa aktarılıyordu. Hata/yükleme sırasında bayat metin yanlış biçim adıyla iniyordu.
  it("akan mesaj değişince yeniden dışa aktarmaz, yeni tamamlanmış mesajda aktarır", async () => {
    const onExport = vi.fn(async () => ({ metin: "# Çekirdek", dosya_adi: "a.md" }));
    const view = render(<ShareDialog messages={[{ rol: "asistan", metin: "Ya", akan: true }]} onClose={vi.fn()} onExport={onExport} title="S" />);
    await vi.waitFor(() => expect(onExport).toHaveBeenCalledTimes(1));
    view.rerender(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt", akan: true }]} onClose={vi.fn()} onExport={onExport} title="S" />);
    view.rerender(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt daha", akan: true }]} onClose={vi.fn()} onExport={onExport} title="S" />);
    await new Promise((r) => setTimeout(r, 0));
    expect(onExport).toHaveBeenCalledTimes(1);
    view.rerender(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={vi.fn()} onExport={onExport} title="S" />);
    await vi.waitFor(() => expect(onExport).toHaveBeenCalledTimes(2));
  });

  it("çekirdek düşerse ve yükleme sürerken 'Dosyaya kaydet' kapalıdır", async () => {
    let resolveJson: ((v: { metin: string; dosya_adi: string }) => void) | undefined;
    const onExport = vi.fn((format: "markdown" | "json") =>
      format === "json"
        ? new Promise<{ metin: string; dosya_adi: string }>((r) => { resolveJson = r; })
        : Promise.resolve({ metin: "# MD", dosya_adi: "a.md" }));
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={vi.fn()} onExport={onExport} title="S" />);
    const kaydet = await screen.findByRole("button", { name: "Dosyaya kaydet" }) as HTMLButtonElement;
    await vi.waitFor(() => expect(kaydet.disabled).toBe(false));
    fireEvent.click(screen.getByLabelText("JSON"));
    expect(kaydet.disabled).toBe(true);
    resolveJson?.({ metin: "{}", dosya_adi: "a.json" });
    await vi.waitFor(() => expect(kaydet.disabled).toBe(false));
    cleanup();
    const bozuk = vi.fn(async () => { throw new Error("yok"); });
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={vi.fn()} onExport={bozuk} title="S" />);
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "Dosyaya kaydet" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
