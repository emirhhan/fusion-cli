import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ChromeBrowser, installChecks } from "./ChromeBrowser";

afterEach(cleanup);

it("Chrome bağlantısı başlatılınca port ve anahtarı gösterir, kapatılınca gizler", async () => {
  let running = false;
  const client = {
    request: vi.fn(async (name: string) => {
      if (name === "chrome.baslat") running = true;
      if (name === "chrome.durdur") running = false;
      return {
        ok: true,
        calisiyor: running,
        bagli: false,
        port: running ? 45123 : null,
        anahtar: name === "chrome.baslat" ? "eşleştirme-anahtarı" : null,
      };
    }),
  } as unknown as ProtocolClient;

  render(<ChromeBrowser client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Bağlantıyı başlat" }));

  expect(await screen.findByDisplayValue("45123")).toBeTruthy();
  expect(screen.getByDisplayValue("eşleştirme-anahtarı")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kapat" }));
  await waitFor(() => expect(screen.queryByDisplayValue("eşleştirme-anahtarı")).toBeNull());
  expect(client.request).toHaveBeenCalledWith("chrome.durdur", {});
});

it("Eklentiyi kur düğmesi kurulumu başlatır, adımları gösterir ve doğrulamayı yansıtır", async () => {
  const client = {
    request: vi.fn(async (name: string) => {
      if (name === "chrome.kur") {
        return {
          ok: true, calisiyor: true, bagli: false, port: 1, anahtar: "a",
          eklenti_yuklu: false, eklenti_etkin: false, yol: "/x", adimlar: ["Geliştirici modunu aç."],
        };
      }
      return { ok: true, calisiyor: false, bagli: false, port: null, anahtar: null, eklenti_yuklu: false };
    }),
  } as unknown as ProtocolClient;

  render(<ChromeBrowser client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Eklentiyi kur" }));

  expect(await screen.findByText("Geliştirici modunu aç.")).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("chrome.kur", {});
});

it("Kurulum tamamlanınca düğme kalkar", async () => {
  const client = {
    request: vi.fn(async () => ({
      ok: true, calisiyor: true, bagli: true, port: 1, anahtar: null, eklenti_yuklu: true, eklenti_etkin: true,
    })),
  } as unknown as ProtocolClient;
  render(<ChromeBrowser client={client} />);
  await screen.findByRole("button", { name: "Bağlantıyı kapat" });
  expect(screen.queryByRole("button", { name: "Eklentiyi kur" })).toBeNull();
});

it("installChecks yüklü-etkin ve eşleşme durumlarını ayırır", () => {
  expect(installChecks(null)).toEqual({ loaded: "off", paired: "off" });
  expect(installChecks({ ok: true, calisiyor: true, bagli: false, port: 1, anahtar: null, eklenti_yuklu: true, eklenti_etkin: false }))
    .toEqual({ loaded: "wait", paired: "wait" });
});

it("yoklama hatası sonraki başarılı yoklamada kalkar; yoklamalar üst üste binmez; anahtar varsayılan gizli (U2-40)", async () => {
  vi.useFakeTimers();
  try {
    let call = 0;
    let resolveSlow: ((value: unknown) => void) | null = null;
    const client = {
      request: vi.fn((name: string) => {
        if (name !== "chrome.durum") return Promise.resolve({ ok: true });
        call += 1;
        if (call === 1) return Promise.reject(new Error("kopuk"));
        if (call === 3) return new Promise((resolve) => { resolveSlow = resolve; });
        return Promise.resolve({ ok: true, calisiyor: true, bagli: false, port: 1234, anahtar: "gizli-anahtar" });
      }),
    } as unknown as ProtocolClient;
    render(<ChromeBrowser client={client} />);
    await act(async () => { await act(async () => { await vi.advanceTimersByTimeAsync(0); }); });
    expect(screen.getByRole("alert").textContent).toContain("okunamadı");
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(screen.queryByRole("alert")).toBeNull();
    const key = screen.getByLabelText("Eşleştirme anahtarı") as HTMLInputElement;
    expect(key.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Anahtarı göster" }));
    expect(key.type).toBe("text");
    // 3. yoklama yavaş: 8 sn içinde yenisi başlamaz.
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    const before = call;
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(call).toBe(before);
    resolveSlow?.({ ok: true, calisiyor: true, bagli: false, port: 1234, anahtar: "gizli-anahtar" });
  } finally { vi.useRealTimers(); }
});

it("eklentinin geliştirici yeteneklerini (konsol/ağ, GIF kaydı, kısayollar) kullanıcıya söyler", async () => {
  const client = {
    request: vi.fn(async () => ({ ok: true, calisiyor: false, bagli: false, port: null, anahtar: null })),
  } as unknown as ProtocolClient;
  render(<ChromeBrowser client={client} />);
  const list = await screen.findByRole("list", { name: "Eklentinin yapabildikleri" });
  expect(list.textContent).toContain("konsolu ve ağ istekleri");
  expect(list.textContent).toContain(".fusion/kayitlar");
  expect(list.textContent).toContain("Shift+F");
});

it("birden çok tarayıcı bağlıyken Bunu kullan seçimi chrome.tarayici_sec ile gönderir (#432)", async () => {
  const client = {
    request: vi.fn(async (name: string) => {
      if (name === "chrome.tarayici_sec") return { ok: true };
      return {
        ok: true, calisiyor: true, bagli: true, port: 1, anahtar: null,
        tarayicilar: [
          { deviceId: "chrome-1", name: "Chrome", inUse: false },
          { deviceId: "edge-1", name: "Edge", inUse: false },
        ],
      };
    }),
  } as unknown as ProtocolClient;

  render(<ChromeBrowser client={client} />);
  expect(await screen.findByText(/Fusion'ın kullanacağını seç/)).toBeTruthy();
  fireEvent.click(screen.getAllByRole("button", { name: "Bunu kullan" })[1]);
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("chrome.tarayici_sec", { deviceId: "edge-1" }));
  expect(await screen.findByText("Kullanılıyor")).toBeTruthy();
});
