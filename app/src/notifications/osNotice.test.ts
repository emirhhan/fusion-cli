import { describe, expect, it, vi } from "vitest";
import { osBildirimiGonder, type OsBildirimBagimliliklari } from "./osNotice";

function bagimliliklar(degisiklik: Partial<OsBildirimBagimliliklari> = {}): OsBildirimBagimliliklari {
  return {
    kabukVar: () => true,
    uygulamaOdakta: () => false,
    izinVerildi: vi.fn(async () => true),
    izinIste: vi.fn(async () => "granted" as const),
    gonder: vi.fn(),
    ...degisiklik,
  };
}

/* Zamanlanmış görev onay beklerken kullanıcı uygulamada olmayabilir; uygulama içi şerit
   yetmez (U5-57). İzin yoksa şerit kalır, bildirim sessizce atlanır. */
describe("osBildirimiGonder", () => {
  it("izin varsa işletim sistemi bildirimi gönderir", async () => {
    const bag = bagimliliklar();
    await expect(osBildirimiGonder("Başlık", "Metin", bag)).resolves.toBe("gonderildi");
    expect(bag.gonder).toHaveBeenCalledWith({ title: "Başlık", body: "Metin" });
    expect(bag.izinIste).not.toHaveBeenCalled();
  });

  it("izin yoksa bir kez ister; verilirse gönderir", async () => {
    const bag = bagimliliklar({ izinVerildi: vi.fn(async () => false) });
    await expect(osBildirimiGonder("B", "M", bag)).resolves.toBe("gonderildi");
    expect(bag.izinIste).toHaveBeenCalledOnce();
    expect(bag.gonder).toHaveBeenCalledOnce();
  });

  it("izin reddedilirse göndermez (uygulama içi şerit kalır)", async () => {
    const bag = bagimliliklar({
      izinVerildi: vi.fn(async () => false),
      izinIste: vi.fn(async () => "denied" as const),
    });
    await expect(osBildirimiGonder("B", "M", bag)).resolves.toBe("izin-yok");
    expect(bag.gonder).not.toHaveBeenCalled();
  });

  it("uygulama odaktayken gönderilmez; şerit zaten görünür", async () => {
    const bag = bagimliliklar({ uygulamaOdakta: () => true });
    await expect(osBildirimiGonder("B", "M", bag)).resolves.toBe("odakta");
    expect(bag.gonder).not.toHaveBeenCalled();
    expect(bag.izinVerildi).not.toHaveBeenCalled();
  });

  it("Tauri kabuğu yoksa (tarayıcı/test) hiçbir şey yapmaz", async () => {
    const bag = bagimliliklar({ kabukVar: () => false });
    await expect(osBildirimiGonder("B", "M", bag)).resolves.toBe("kabuk-yok");
    expect(bag.izinVerildi).not.toHaveBeenCalled();
  });

  it("eklenti hatası yutulur; çağıranı bozmaz", async () => {
    const bag = bagimliliklar({ izinVerildi: vi.fn(async () => { throw new Error("eklenti yok"); }) });
    await expect(osBildirimiGonder("B", "M", bag)).resolves.toBe("hata");
  });
});
