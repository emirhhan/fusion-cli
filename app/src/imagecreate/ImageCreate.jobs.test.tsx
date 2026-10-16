import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ImageCreate } from "./ImageCreate";
import { ImageJobJournal } from "./imageJobJournal";

beforeEach(() => localStorage.clear());
afterEach(cleanup);
const result = (jobId: string) => ({ ok: true, jobId, state: "completed", saglayici: "Offline", dosyalar: [{ yol: "/gallery/result.png", genislik: 9, yukseklik: 6, sha256: "a".repeat(64) }] });
function clientFor(handler: (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>) {
  return { request: vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "gorsel.saglayicilar") return { ok: true, isProtokolu: 1, secenekler: [{ deger: "offline", etiket: "Offline", referans: false }] };
    if (name === "gorsel.galeri") return { ok: true, dosyalar: [] };
    if (name === "gorsel.akislar") return { ok: true, akislar: [] };
    if (name === "gorsel.is.liste") return { ok: true, isler: [], sonraki: null };
    return handler(name, data);
  }) };
}
it("yeni backend yeteneğinde legacy üretim yerine kimliği önceden kaydedilmiş işi çalıştırır", async () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  const client = clientFor(async (name, data) => {
    expect(name).toBe("gorsel.is.baslat");
    expect(journal.read()).toContain(data.requestId);
    return result(String(data.requestId));
  });
  render(<ImageCreate client={client} jobScope="scope" toUrl={(path) => path} />);
  await waitFor(() => expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "deneme" } });
  fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
  expect(await screen.findByRole("img", { name: "deneme" })).toBeTruthy();
  expect(client.request.mock.calls.some(([name]) => name === "gorsel.olustur")).toBe(false);
  expect(journal.read()).toEqual([]);
});
it("yeniden açılışta belirsiz iş yeni üretimi engeller, kontrol yalnız durumu okur", async () => {
  new ImageJobJournal(localStorage, "scope").add("old-job");
  const client = clientFor(async (name) => {
    expect(name).toBe("gorsel.is.durum");
    return result("old-job");
  });
  render(<ImageCreate client={client} jobScope="scope" toUrl={(path) => path} />);
  await screen.findByRole("button", { name: "Durumu kontrol et" });
  expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Durumu kontrol et" }));
  expect(await screen.findByRole("img", { name: "Toparlanan görsel" })).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole("button", { name: "Durumu kontrol et" })).toBeNull());
  expect(client.request.mock.calls.some(([name]) => name === "gorsel.is.baslat")).toBe(false);
});
it("kapsam yoksa yeni protokolü legacy üretime düşürmez", async () => {
  const client = clientFor(async () => { throw new Error("üretim olmamalı"); });
  render(<ImageCreate client={client} />);
  expect(await screen.findByText(/Sohbet kapsamı/)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(true);
});
it("iptal temizliği doğrulanana kadar yeni üretimi açmaz", async () => {
  let finishCancel!: (value: Record<string, unknown>) => void;
  let jobId = "";
  const client = clientFor(async (name, data) => {
    if (name === "gorsel.is.baslat") { jobId = String(data.requestId); return { ok: true, jobId, state: "running", dosyalar: [] }; }
    if (name === "gorsel.is.iptal") return new Promise((resolve) => { finishCancel = resolve; });
    return new Promise(() => {});
  });
  render(<ImageCreate client={client} jobScope="scope" toUrl={(path) => path} />);
  await waitFor(() => expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "deneme" } });
  fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
  fireEvent.click(await screen.findByRole("button", { name: "Üretimi durdur" }));
  await waitFor(() => expect(finishCancel).toBeTypeOf("function"));
  expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(true);
  finishCancel({ ok: false, jobId, state: "cancelled", dosyalar: [] });
  await waitFor(() => expect(screen.queryByRole("button", { name: "Üretimi durdur" })).toBeNull());
  await waitFor(() => expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(false));
  expect(new ImageJobJournal(localStorage, "scope").read()).toEqual([]);
});
