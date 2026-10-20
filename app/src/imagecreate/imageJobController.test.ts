import { beforeEach, expect, it, vi } from "vitest";
import { ImageJobController } from "./imageJobController";
import { ImageJobJournal } from "./imageJobJournal";

beforeEach(() => localStorage.clear());
const completed = (jobId: string) => ({ ok: true, jobId, state: "completed", dosyalar: [{ yol: "/gallery/a.png", genislik: 9, yukseklik: 6, sha256: "a".repeat(64) }] });
const page = { ok: true, isler: [], sonraki: null };

it("üretimden önce kimliği kaydeder; doğrulanmış terminalden sonra temizler", async () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "gorsel.is.liste") return page;
    expect(journal.read()).toEqual(["new-job"]);
    return completed(String(data.requestId));
  });
  const controller = new ImageJobController(request, journal, () => {}, () => "new-job");
  await controller.initialize();
  expect((await controller.start({ istem: "deneme" })).state).toBe("completed");
  expect(journal.read()).toEqual([]);
  expect(controller.state.jobs).toEqual([]);
});
it("yeniden açılan belirsiz işi izler; yeni üretim başlatmaz", async () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  journal.add("old-job");
  const request = vi.fn(async (name: string) => name === "gorsel.is.liste" ? page : completed("old-job"));
  const controller = new ImageJobController(request, journal, () => {});
  await controller.initialize();
  await expect(controller.start({ istem: "deneme" })).rejects.toThrow(/kontrol/);
  expect((await controller.observe("old-job")).state).toBe("completed");
  expect(request.mock.calls.every(([name]) => name !== "gorsel.is.baslat")).toBe(true);
  expect(journal.read()).toEqual([]);
  expect(controller.state.jobs).toEqual([]);
});
it("sunucuda çalışan iş de yeni üretimi engeller ve yalnız açık iptal çağrılır", async () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  const request = vi.fn(async (name: string) => name === "gorsel.is.liste"
    ? { ...page, isler: [{ jobId: "live-job", state: "running", outputsVerified: false }] }
    : { ok: false, jobId: "live-job", state: "cancelled", dosyalar: [] });
  const controller = new ImageJobController(request, journal, () => {});
  await controller.initialize();
  await expect(controller.start({})).rejects.toThrow();
  expect((await controller.cancel("live-job")).state).toBe("cancelled");
  expect(journal.read()).toEqual([]);
  expect(controller.state.jobs).toEqual([]);
});
it("sahibi kapanınca geç sonuç UI'ye yazılmaz ve belirsiz kimlik korunur", async () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  let resolve!: (value: Record<string, unknown>) => void;
  const request = vi.fn(async (name: string) => name === "gorsel.is.liste" ? page : new Promise<Record<string, unknown>>((done) => { resolve = done; }));
  const notify = vi.fn();
  const controller = new ImageJobController(request, journal, notify, () => "new-job");
  await controller.initialize();
  const pending = controller.start({});
  controller.dispose();
  const calls = notify.mock.calls.length;
  resolve(completed("new-job"));
  await pending;
  expect(notify).toHaveBeenCalledTimes(calls);
  expect(journal.read()).toEqual(["new-job"]);
});
