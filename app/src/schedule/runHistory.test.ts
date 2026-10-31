import { describe, expect, it, vi } from "vitest";
import { recordScheduleRun, runNotice, runOutcome, scheduleRuns } from "./runHistory";
import type { ScheduledTask } from "./types";

const gorev = { id: "g1", baslik: "Stok raporu", gorev: "rapor", kok: "/p", etkin: true, sonraki: null, son_calisma: null, tur: "aralik" } as ScheduledTask;

describe("zamanlanmış görev çalışma geçmişi (P-038)", () => {
  it("son nihai cevabı özetler, hata ve ara notu ayırır", () => {
    expect(runOutcome([{ rol: "asistan", metin: "Rapor   hazır" }, { rol: "asistan", metin: "◎ not", ara: true }]))
      .toEqual({ durum: "tamam", ozet: "Rapor hazır" });
    expect(runOutcome([{ rol: "asistan", metin: "Sağlayıcı hatası", hata: true }]).durum).toBe("hata");
    expect(runOutcome([{ rol: "kullanici", metin: "x" }]).durum).toBe("hata");
  });

  it("geçmişi çekirdeğe yazar ve bildirim metni üretir", async () => {
    const request = vi.fn().mockResolvedValue({ ok: true });
    expect(await recordScheduleRun({ request }, gorev, "s1", { durum: "tamam", ozet: "ok" })).toBe(true);
    expect(request).toHaveBeenCalledWith("zamanlama.calisma_kaydet", { id: "g1", sohbet_id: "s1", durum: "tamam", ozet: "ok" });
    expect(runNotice(gorev, { durum: "hata", ozet: "kota" }).baslik).toContain("hatayla");
  });

  it("bozuk geçmiş satırlarını düşürür", () => {
    expect(scheduleRuns([{ zaman: 1, sohbet_id: "s", durum: "tamam", ozet: "a" }, { zaman: "x" }, null])).toHaveLength(1);
    expect(scheduleRuns("bozuk")).toEqual([]);
  });
});
