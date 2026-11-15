import { describe, expect, it } from "vitest";
import { planKartiOku } from "./planCard";

describe("planKartiOku", () => {
  it("çekirdeğin seçeneklerini sırasıyla okur", () => {
    const kart = planKartiOku({
      ok: true,
      bekliyor: true,
      secenekler: [
        { deger: "clear:edits", etiket: "Evet, bağlamı temizle ve düzenlemeleri otomatik kabul et", aciklama: "x" },
        { deger: "edits", etiket: "Evet, düzenlemeleri otomatik kabul et" },
        { deger: 3, etiket: "bozuk" },
      ],
      onerilen: "Evet, bağlamı temizle ve düzenlemeleri otomatik kabul et",
    });
    expect(kart?.secenekler.map((item) => item.deger)).toEqual(["clear:edits", "edits"]);
    expect(kart?.secenekler[1].aciklama).toBe("");
    expect(kart?.onerilen).toContain("bağlamı temizle");
  });

  it("bekleyen plan yoksa kart açılmaz", () => {
    expect(planKartiOku({ ok: true, bekliyor: false, secenekler: [] })).toBeNull();
    expect(planKartiOku(null)).toBeNull();
    expect(planKartiOku({ bekliyor: true, secenekler: [] })).toBeNull();
  });
});
