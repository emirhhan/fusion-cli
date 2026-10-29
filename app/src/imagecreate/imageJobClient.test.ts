import { describe, expect, it, vi } from "vitest";
import { cancelImageJob, observeImageJob } from "./imageJobClient";

const output = { ok: true, jobId: "stable", state: "completed", dosyalar: [{ yol: "/gallery/a.png", genislik: 12, yukseklik: 7, sha256: "a".repeat(64) }] };
const fast = { intervalMs: 0, requestTimeoutMs: 20, maxPolls: 3 };

describe("kalıcı görsel işi gözlemcisi", () => {
  it("kayıp başlangıç yanıtını durum okuyarak bulur; üretimi tekrarlamaz", async () => {
    const request = vi.fn().mockRejectedValueOnce(new Error("lost ack")).mockResolvedValueOnce(output);
    expect(await observeImageJob(request, "stable", { ...fast, start: { istem: "deneme" } })).toEqual(output);
    expect(request.mock.calls.map(([name]) => name)).toEqual(["gorsel.is.baslat", "gorsel.is.durum"]);
    expect(request.mock.calls[0][1].requestId).toBe("stable");
  });
  it("yalnız gözlem yeniden açıldığında başlangıç göndermez", async () => {
    const request = vi.fn().mockResolvedValue(output);
    expect((await observeImageJob(request, "stable", fast)).state).toBe("completed");
    expect(request).toHaveBeenCalledOnce();
    expect(request.mock.calls[0][0]).toBe("gorsel.is.durum");
  });
  it("başlangıç zaman aşımı aynı kimlikle okunur; geç yanıt sonucu değiştirmez", async () => {
    let late!: (value: Record<string, unknown>) => void;
    const request = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { late = resolve; })).mockResolvedValueOnce(output);
    const result = await observeImageJob(request, "stable", { ...fast, start: {} });
    late({ ok: true, jobId: "wrong", state: "running" });
    expect(result).toEqual(output);
    expect(request).toHaveBeenCalledTimes(2);
  });
  it("bulunamayan kabulü yeni üretime dönüştürmez", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, code: "job_not_found" });
    const result = await observeImageJob(request, "stable", fast);
    expect(result).toMatchObject({ ok: false, jobId: "stable", state: "recoveryRequired" });
    expect(request.mock.calls.every(([name]) => name === "gorsel.is.durum")).toBe(true);
  });
  it("kabul öncesi kesin ret iş kaydı oluşturmaz; kayıp iş gibi toparlanmaya düşmez", async () => {
    const ret = { ok: false, code: "invalid_request", metin: "Referans görsel doğrulanamadı." };
    const request = vi.fn().mockResolvedValue(ret);
    const result = await observeImageJob(request, "stable", { ...fast, start: { referans: "/gallery/silindi.png" } });
    expect(result).toMatchObject({ ok: false, jobId: "stable", state: "failed", code: "invalid_request", metin: ret.metin });
    // Hiç iş kabul edilmediği için durum sorgusu yapılmaz.
    expect(request.mock.calls.map(([name]) => name)).toEqual(["gorsel.is.baslat"]);
  });
  it("depo hatası gibi belirsiz ret toparlanma gerektirmeye devam eder", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, code: "storage_failed", metin: "x" });
    expect(await observeImageJob(request, "stable", { ...fast, start: {} })).toMatchObject({ state: "recoveryRequired" });
  });
  it("iptal edilen gözlem uzak işi iptal etmiş gibi göstermez", async () => {
    const controller = new AbortController();
    const request = vi.fn(() => new Promise<Record<string, unknown>>(() => {}));
    const pending = observeImageJob(request, "stable", { ...fast, signal: controller.signal });
    controller.abort();
    expect(await pending).toMatchObject({ ok: false, code: "observation_stopped", state: "recoveryRequired" });
    expect(request.mock.calls).toHaveLength(1);
  });
  it.each([
    { ...output, jobId: "other" },
    { ...output, state: "future-state" },
    { ...output, dosyalar: [] },
    { ...output, dosyalar: [{ yol: "/gallery/a.png", genislik: 12, yukseklik: 7 }] },
    { ...output, dosyalar: [{ yol: "/gallery/a.png", genislik: 0, yukseklik: 7, sha256: "a".repeat(64) }] },
  ])("bozuk veya başka işe ait başarıyı kabul etmez", async (payload) => {
    const result = await observeImageJob(vi.fn().mockResolvedValue(payload), "stable", fast);
    expect(result).toMatchObject({ ok: false, state: "recoveryRequired" });
  });
});

it("başarısız durum istekleri arasında da gözlem aralığını korur", async () => {
  vi.useFakeTimers();
  try {
    const request = vi.fn().mockRejectedValue(new Error("offline"));
    const pending = observeImageJob(request, "stable", { ...fast, intervalMs: 1000 });
    await vi.advanceTimersByTimeAsync(0);
    expect(request).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(request).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(request).toHaveBeenCalledTimes(2);
    await vi.runAllTimersAsync();
    expect((await pending).state).toBe("recoveryRequired");
  } finally { vi.useRealTimers(); }
});

it("iptal yanıtı doğrulanmadan durdu sonucu üretmez", async () => {
  const { cancelImageJob } = await import("./imageJobClient");
  const request = vi.fn().mockResolvedValue({ ok: false, jobId: "stable", state: "cancelled", dosyalar: [] });
  expect(await cancelImageJob(request, "stable", fast)).toMatchObject({ state: "cancelled" });
  expect(request.mock.calls[0][0]).toBe("gorsel.is.iptal");
  expect(await cancelImageJob(vi.fn().mockRejectedValue(new Error("offline")), "stable", fast)).toMatchObject({ state: "recoveryRequired" });
});

// Ölçüldü (29 Ekim, U3-08): sunucu bilinmeyen iş için {ok:false, code:"job_not_found"} döner;
// istemci bunu kimliksiz sayıp 1200 tur (~20 dk) boyunca "izleniyor" bırakıyor, kullanıcı
// işin gerçekten kayıtsız olduğunu hiç öğrenemiyordu.
describe("bilinmeyen iş", () => {
  it("yalnız gözlemde job_not_found hemen döner ve kodu korur", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, code: "job_not_found", metin: "Bu kapsamda görsel işi bulunamadı." });
    const result = await observeImageJob(request, "stable", { ...fast, maxPolls: 50 });
    expect(result).toMatchObject({ ok: false, jobId: "stable", state: "recoveryRequired", code: "job_not_found" });
    expect(request).toHaveBeenCalledOnce();
    expect(result.metin).toMatch(/bulunamadı/);
  });
  it("iptalde job_not_found kodu korunur", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, code: "job_not_found" });
    expect(await cancelImageJob(request, "stable", fast)).toMatchObject({ state: "recoveryRequired", code: "job_not_found" });
  });
});
