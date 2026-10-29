import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtocolClient, RequestAbortedError, RequestTimeoutError } from "./client";

// U5-01: RPC isteğinin merkezi son süresi yoktu; çekirdek cevap vermezse istek sonsuza
// dek asılı kalıyordu. Süresi dolan isteğin geç gelen sonucu başka isteğe yazılmamalı.
function sahteTasima() {
  const yazilan: { id: string; ad: string }[] = [];
  let dinleyici: ((satir: string) => void) | null = null;
  return {
    yazilan,
    gonder: (satir: string) => yazilan.push(JSON.parse(satir)),
    dinle: (f: (satir: string) => void) => {
      dinleyici = f;
    },
    sonuc: (id: string, veri: Record<string, unknown>) =>
      dinleyici?.(JSON.stringify({ tip: "sonuc", id, veri })),
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ProtocolClient son süre ve iptal", () => {
  it("süresi dolan istek açık hatayla reddedilir, geç sonuç başka isteğe yazılmaz", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const ilk = c.request("uzun.is", {}, { timeoutMs: 1000 });
    const ilkHata = expect(ilk).rejects.toBeInstanceOf(RequestTimeoutError);
    vi.advanceTimersByTime(1000);
    await ilkHata;

    const ikinci = c.request("kisa.is", {});
    t.sonuc(t.yazilan[0].id, { ok: true, kimin: "ilk" });
    t.sonuc(t.yazilan[1].id, { ok: true, kimin: "ikinci" });

    await expect(ikinci).resolves.toEqual({ ok: true, kimin: "ikinci" });
  });

  it("AbortSignal bekleyen isteği iptal eder; önceden iptal edilmiş istek gönderilmez", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const denetci = new AbortController();
    const bekleyen = c.request("proje.listele", {}, { signal: denetci.signal });
    denetci.abort();
    await expect(bekleyen).rejects.toBeInstanceOf(RequestAbortedError);

    const iptalli = new AbortController();
    iptalli.abort();
    await expect(c.request("proje.oku", {}, { signal: iptalli.signal })).rejects.toBeInstanceOf(
      RequestAbortedError,
    );
    expect(t.yazilan).toHaveLength(1);
  });

  it("başarılı cevapta zamanlayıcı temizlenir", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const bekleyen = c.request("proje.oku", {}, { timeoutMs: 5000 });
    t.sonuc(t.yazilan[0].id, { ok: true });
    await bekleyen;

    expect(vi.getTimerCount()).toBe(0);
  });

  it("çalışma alanı okumalarına varsayılan son süre uygulanır, uzun işlere uygulanmaz", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const okuma = c.request("proje.oku", { yol: "a.txt" });
    const okumaHata = expect(okuma).rejects.toBeInstanceOf(RequestTimeoutError);
    const tur = c.request("tur.calistir", { gorev: "uzun iş" });
    let turBitti = false;
    void tur.then(() => (turBitti = true), () => (turBitti = true));

    vi.advanceTimersByTime(10 * 60 * 1000);
    await okumaHata;
    await Promise.resolve();

    expect(turBitti).toBe(false);
  });

  // U5-01 — Ölçüldü (29 Ekim): web.dogrula/web.arac_olc/web.giris ve ProviderList istekleri süresizdi;
  // sessiz çekirdekte panel `busy` kilidinde kalıyordu.
  it.each([
    ["web.giris", 60_000], ["web.giris_durumu", 30_000], ["web.baglan", 30_000], ["web.cikis", 30_000],
    ["web.dogrula", 120_000], ["web.arac_olc", 300_000], ["saglayici.katalog", 30_000],
    ["web.model_secenekleri", 60_000], ["web.model_sec", 60_000], ["kontrol.anahtar_dogrula", 90_000],
  ])("%s sessiz çekirdekte %i ms sonra reddedilir", async (ad, sure) => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const istek = c.request(ad, {});
    const hata = expect(istek).rejects.toBeInstanceOf(RequestTimeoutError);
    vi.advanceTimersByTime(sure - 1);
    await Promise.resolve();
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(1);
    await hata;
  });

  it("close bekleyen zamanlayıcıları da temizler", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const bekleyen = c.request("uzun.is", {}, { timeoutMs: 1000 });
    c.close();
    await expect(bekleyen).rejects.toThrow();

    expect(vi.getTimerCount()).toBe(0);
  });
});
