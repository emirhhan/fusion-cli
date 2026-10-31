import { describe, expect, it } from "vitest";
import { addressFromInput, decodePick, decodeSnapshot, keyAction, normalizedPoint } from "./browserPanelProtocol";

const tus = (key: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  keyAction({ key, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("tarayıcı paneli protokolü (P-045)", () => {
  it("yazılabilir karakteri metin, özel tuşu ve kısayolu Playwright adıyla gönderir", () => {
    expect(tus("ş")).toEqual({ tur: "yaz", metin: "ş" });
    expect(tus("A", { shiftKey: true })).toEqual({ tur: "yaz", metin: "A" });
    expect(tus("Enter")).toEqual({ tur: "tus", tus: "Enter" });
    expect(tus("Tab", { shiftKey: true })).toEqual({ tur: "tus", tus: "Shift+Tab" });
    expect(tus("a", { metaKey: true })).toEqual({ tur: "tus", tus: "Meta+a" });
    // Kopyala/yapıştır uygulamaya kalır; yapıştırma `paste` olayıyla metin olarak gider.
    expect(tus("v", { metaKey: true })).toBeNull();
    expect(tus("Shift")).toBeNull();
  });

  it("görüntü üstündeki konumu 0..1 aralığına çevirir, dışarısı yok sayılır", () => {
    const rect = { left: 10, top: 20, width: 200, height: 100 };
    expect(normalizedPoint(110, 70, rect)).toEqual({ x: 0.5, y: 0.5 });
    expect(normalizedPoint(5, 70, rect)).toBeNull();
    expect(normalizedPoint(1, 1, { ...rect, width: 0 })).toBeNull();
  });

  it("şemasız adrese yerelse http, değilse https ekler", () => {
    expect(addressFromInput("localhost:5173/a")).toBe("http://localhost:5173/a");
    expect(addressFromInput("ornek.com")).toBe("https://ornek.com");
    expect(addressFromInput(" https://x.dev ")).toBe("https://x.dev");
    expect(addressFromInput("  ")).toBe("");
  });

  it("kare yükünü ve bozuk alanları güvenle çözer", () => {
    const snap = decodeSnapshot({
      ok: true, acik: true, seq: 3, url: "https://a.dev/", baslik: "A", denetim: "kullanici",
      sekmeler: [{ no: 1, baslik: "A", url: "https://a.dev/", etkin: true }, { bozuk: true }],
      kare: { base64: "QUJD", mime: "image/jpeg", genislik: 1280, yukseklik: 800 },
    });
    expect(snap.denetim).toBe("kullanici");
    expect(snap.sekmeler).toHaveLength(1);
    expect(snap.kare?.genislik).toBe(1280);
    expect(decodeSnapshot({ ok: true, acik: false }).kare).toBeNull();
    expect(() => decodePick({ ok: false, metin: "Bu noktada seçilebilir öğe yok." })).toThrow("seçilebilir öğe yok");
  });
});
