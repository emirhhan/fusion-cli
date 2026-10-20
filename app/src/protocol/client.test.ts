import { describe, expect, it } from "vitest";
import { ProtocolClient } from "./client";

/** Testte gerçek süreç yok: satır gönderen/alan sahte bir taşıma kullanılır. */
function sahteTasima() {
  const yazilan: string[] = [];
  let dinleyici: ((satir: string) => void) | null = null;
  return {
    yazilan,
    gonder: (satir: string) => yazilan.push(satir),
    dinle: (f: (satir: string) => void) => {
      dinleyici = f;
    },
    al: (satir: string) => dinleyici?.(satir),
  };
}

describe("ProtocolClient", () => {
  it("istek gönderir ve sonucu eşleştirir", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);

    const bekleyen = c.request("oturum.durum", {});
    const gonderilen = JSON.parse(t.yazilan[0]);
    expect(gonderilen.tip).toBe("istek");
    expect(gonderilen.ad).toBe("oturum.durum");

    t.al(JSON.stringify({ tip: "sonuc", id: gonderilen.id, veri: { ok: true, kok: "/x" } }));
    await expect(bekleyen).resolves.toEqual({ ok: true, kok: "/x" });
  });

  it("olayları dinleyiciye iletir", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const gorulen: unknown[] = [];
    c.onEvent((e) => gorulen.push(e));

    t.al(JSON.stringify({ tip: "olay", veri: { olay: "TurnFinished" } }));

    expect(gorulen).toEqual([{ olay: "TurnFinished" }]);
  });

  it("soruyu iletir ve cevabı aynı kimlikle yollar", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    let gelenKimlik = "";
    c.onQuestion((id) => {
      gelenKimlik = id;
    });

    t.al(JSON.stringify({ tip: "soru", id: "12", veri: { tur: "onay" } }));
    c.reply(gelenKimlik, { secim: "once" });

    expect(JSON.parse(t.yazilan[0])).toEqual({ tip: "cevap", id: "12", veri: { secim: "once" } });
  });

  it("bozuk satır istemciyi düşürmez", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const gorulen: unknown[] = [];
    c.onEvent((e) => gorulen.push(e));

    expect(() => t.al("{bozuk")).not.toThrow();
    t.al(JSON.stringify({ tip: "olay", veri: { olay: "X" } }));

    expect(gorulen).toEqual([{ olay: "X" }]);
  });

  it("eşleşmeyen sonuç kimliği yok sayılır", () => {
    const t = sahteTasima();
    // İstemci kurulur ve dinlemeye başlar; bu testte örneğe doğrudan
    // erişilmez, sınanan şey gelen satırın istisna fırlatmadan yutulmasıdır.
    new ProtocolClient(t.gonder, t.dinle);

    expect(() => t.al(JSON.stringify({ tip: "sonuc", id: "yok", veri: {} }))).not.toThrow();
  });

  // KANIT: bu test close() içindeki reddet() çağrısı kaldırılıp (bekleyen'i
  // yalnız sessizce temizleyecek şekilde) geçici olarak geri alındığında
  // KIRMIZI koşar — istek sonsuza dek ne çözülür ne reddedilir, aşağıdaki
  // `await` zaman aşımına takılıp test başarısız olur. Test seviyesindeki
  // zaman aşımı (3000ms) bu KIRMIZI koşunun sonsuza dek asılı kalmasını önler.
  it(
    "çekirdek kapandığında bekleyen istek REDDEDİLİR (sonsuza dek asılı kalmaz)",
    async () => {
      const t = sahteTasima();
      const c = new ProtocolClient(t.gonder, t.dinle);

      const bekleyen = c.request("oturum.durum", {});
      c.close("çekirdek kapandı");

      await expect(bekleyen).rejects.toThrow("çekirdek kapandı");
    },
    3000,
  );

  it("close() sonrası gelen satırlar yok sayılır", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const gorulen: unknown[] = [];
    c.onEvent((e) => gorulen.push(e));

    c.close();
    t.al(JSON.stringify({ tip: "olay", veri: { olay: "kapanış-sonrası" } }));

    expect(gorulen).toEqual([]);
  });

  it("close() sonrası yeni istek hemen reddedilir", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);

    c.close();

    await expect(c.request("oturum.durum", {})).rejects.toThrow();
  });
});
