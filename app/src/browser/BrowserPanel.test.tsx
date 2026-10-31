import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { BrowserPanel } from "./BrowserPanel";

afterEach(cleanup);

interface Durum { acik: boolean; denetim: string; kullanici_profili: string; tur_suruyor: boolean; ajan_goruyor: boolean; ajan_bekliyor: boolean }

function istemci(baslangic: Partial<Durum> = {}) {
  const durum: Durum = {
    acik: false, denetim: "ajan", kullanici_profili: "", tur_suruyor: false, ajan_goruyor: true, ajan_bekliyor: false, ...baslangic,
  };
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    const ad = name.replace("tarayici_panel.", "");
    if (ad === "durum") return { ok: true, ...durum, profiller: ["tarayici-paneli", "is"], panel_profili: "tarayici-paneli" };
    if (ad === "ac") { durum.acik = true; return { ok: true, ...durum }; }
    if (ad === "birak") { durum.denetim = "ajan"; return { ok: true, ...durum }; }
    if (ad === "profil") { durum.kullanici_profili = String(data.ad); return { ok: true, ...durum, ajan_goruyor: false }; }
    if (ad === "kare") {
      if (!durum.acik) return { ok: true, ...durum, seq: 0 };
      return {
        ok: true, ...durum, seq: 1, url: "https://ornek.dev/", baslik: "Örnek",
        sekmeler: [{ no: 1, baslik: "Örnek", url: "https://ornek.dev/", etkin: true }],
        ...(data.son === 0 ? { kare: { base64: "QUJD", mime: "image/jpeg", genislik: 1280, yukseklik: 800 } } : {}),
      };
    }
    if (ad === "oge_sec") {
      return { ok: true, secici: "#kaydet", etiket: "button", metin: "Tarayıcıda seçilen öğe…", yol: ".fusion/secimler/oge-1.png", kutu: null };
    }
    return { ok: true, ...durum };
  });
  return { request, onEvent: () => () => undefined } as unknown as ProtocolClient & { request: typeof request };
}

async function goruntu(): Promise<HTMLImageElement> {
  const img = (await screen.findByAltText("Örnek canlı görüntüsü")) as HTMLImageElement;
  img.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
  return img;
}

describe("BrowserPanel (uygulama içi tarayıcı, P-045)", () => {
  it("kapalıyken anlatır, adres yazılınca tarayıcıyı açar ve canlı görüntü ile sekmeyi gösterir", async () => {
    const client = istemci();
    render(<BrowserPanel client={client} />);

    expect(await screen.findByText("Uygulama içi tarayıcı")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Tarayıcı adresi"), { target: { value: "ornek.dev" } });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.ac", { url: "https://ornek.dev" }));
    await goruntu();
    expect(screen.getByRole("tab", { name: "Örnek" }).getAttribute("aria-selected")).toBe("true");
  });

  it("görüntüye tıklama sayfanın 0..1 konumuyla çekirdeğe gider, yazı metin olarak gider", async () => {
    const client = istemci({ acik: true });
    render(<BrowserPanel client={client} />);
    const img = await goruntu();

    fireEvent.click(img, { clientX: 50, clientY: 25, detail: 1 });
    fireEvent.keyDown(img.parentElement as HTMLElement, { key: "ğ" });
    fireEvent.keyDown(img.parentElement as HTMLElement, { key: "Enter" });

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.tikla", { x: 0.25, y: 0.25, tik: 1 }));
    expect(client.request).toHaveBeenCalledWith("tarayici_panel.yaz", { metin: "ğ" });
    expect(client.request).toHaveBeenCalledWith("tarayici_panel.tus", { tus: "Enter" });
  });

  it("kullanıcı denetimdeyken uyarı gösterir; Ajana bırak denetimi geri verir", async () => {
    const client = istemci({ acik: true, denetim: "kullanici", tur_suruyor: true });
    render(<BrowserPanel client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Ajana bırak" }));

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.birak", {}));
  });

  it("ajan aracı denetimi beklerken bunu açıkça söyler", async () => {
    const client = istemci({ acik: true, denetim: "kullanici", tur_suruyor: true, ajan_bekliyor: true });
    render(<BrowserPanel client={client} />);
    expect((await screen.findByText("Ajan seni bekliyor.")).closest("[role=status]")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ajana bırak" })).toBeTruthy();
  });

  it("ajan çalışırken Devral düğmesi görünür", async () => {
    const client = istemci({ acik: true, tur_suruyor: true });
    render(<BrowserPanel client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Devral" }));
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.devral", {}));
  });

  it("öğe seçici açıkken tıklama sayfaya gitmez; seçilen öğe sohbete verilir", async () => {
    const client = istemci({ acik: true });
    const onPick = vi.fn();
    render(<BrowserPanel client={client} onPick={onPick} />);
    const img = await goruntu();

    fireEvent.click(screen.getByRole("button", { name: "Öğe seç ve sohbete ekle" }));
    fireEvent.click(img, { clientX: 100, clientY: 50, detail: 1 });

    await waitFor(() => expect(onPick).toHaveBeenCalledWith({ metin: "Tarayıcıda seçilen öğe…", yol: ".fusion/secimler/oge-1.png" }));
    expect(client.request).toHaveBeenCalledWith("tarayici_panel.oge_sec", { x: 0.5, y: 0.5 });
    expect(client.request).not.toHaveBeenCalledWith("tarayici_panel.tikla", expect.anything());
  });

  it("kalıcı panel oturumu seçilince girişli oturum onayı ayrıca istenir", async () => {
    const client = istemci({ acik: true });
    render(<BrowserPanel client={client} />);

    const secici = await screen.findByRole("combobox", { name: "Tarayıcı oturumu" });
    await waitFor(() => expect((secici as HTMLSelectElement).options).toHaveLength(3));
    fireEvent.change(secici, { target: { value: "tarayici-paneli" } });

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.profil", { ad: "tarayici-paneli" }));
    const onay = await screen.findByRole("checkbox", { name: "Ajan girişli oturumu kullanabilir" });
    expect((onay as HTMLInputElement).checked).toBe(false);
    fireEvent.click(onay);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.ayar", { anahtar: "profil_onayi", deger: true }));
  });

  it("önizlemeden gelen öğe seçme isteği adresi açar ve seçiciyi etkinleştirir", async () => {
    const client = istemci();
    render(<BrowserPanel client={client} request={{ url: "http://localhost:5173/", pick: true, seq: 1 }} />);

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("tarayici_panel.ac", { url: "http://localhost:5173/" }));
    const dugme = await screen.findByRole("button", { name: "Öğe seç ve sohbete ekle" });
    expect(dugme.getAttribute("aria-pressed")).toBe("true");
  });
});
