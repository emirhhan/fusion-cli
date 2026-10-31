import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { PluginsPanel, componentSummary } from "./PluginsPanel";

afterEach(cleanup);

const bilesen = { beceri: 2, komut: 1, ajan: 0, stil: 0, kanca: true, mcp: false };
const onizleme = { ad: "bicimci", surum: "0.1.0", aciklama: "Biçimler", yazar: "Ekip", bilesenler: bilesen, kanca_sayisi: 1, mcp: [], calistirilabilir: true, baglam_maliyeti: 42, uyarilar: ["plugin.json yok"], hatalar: [] };

function client() {
  let kurulu: Record<string, unknown>[] = [];
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "eklenti.listele") return { ok: true, hepsi_kapali: false, eklentiler: kurulu, pazarlar: [] };
    if (name === "eklenti.onizle") return { ok: true, onizleme };
    if (name === "eklenti.kur") {
      kurulu = [{ ad: "bicimci", surum: "0.1.0", aciklama: "Biçimler", durum: "etkin", ayrinti: "", kaynak: String(data.kaynak), pazar: "", etkin: true, calistirilabilir: true, bilesenler: bilesen }];
      return { ok: true, yenile: true, eklenti: kurulu[0] };
    }
    if (name === "eklenti.etkinlik") {
      kurulu = kurulu.map((item) => ({ ...item, etkin: data.etkin, durum: data.etkin ? "etkin" : "kapalı" }));
      return { ok: true, yenile: true, hepsi_kapali: false, eklentiler: kurulu, pazarlar: [] };
    }
    if (name === "eklenti.kaldir") { kurulu = []; return { ok: true, yenile: true, eklentiler: [], pazarlar: [] }; }
    return { ok: false, metin: "bilinmeyen" };
  });
  return { request } as unknown as ProtocolClient & { request: typeof request };
}

it("önizleme gösterir, çalıştırılabilir eklentiyi onayla kurar, kapatır ve iki adımda kaldırır", async () => {
  const api = client();
  const changed = vi.fn();
  render(<PluginsPanel client={api} onChanged={changed} />);
  expect(await screen.findByText(/Kurulu eklenti yok/)).toBeTruthy();

  fireEvent.change(screen.getByRole("textbox", { name: "Eklenti kaynağı" }), { target: { value: "./bicimci" } });
  fireEvent.click(screen.getByRole("button", { name: "Önizle" }));
  expect(await screen.findByRole("note")).toBeTruthy();
  expect(screen.getByText(/bağlam ~42 token/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Onaylıyorum, kur" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.kur", { kaynak: "./bicimci", onay: true }));
  expect(await screen.findByText("bicimci 0.1.0")).toBeTruthy();
  expect(changed).toHaveBeenCalled();

  fireEvent.click(screen.getByRole("switch", { name: "bicimci etkin" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.etkinlik", { ad: "bicimci", etkin: false }));

  fireEvent.click(screen.getByRole("button", { name: "Kaldır" }));
  fireEvent.click(screen.getByRole("button", { name: "Evet, kaldır" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.kaldir", { ad: "bicimci" }));
  expect(await screen.findByText(/Kurulu eklenti yok/)).toBeTruthy();
});

it("hatalı önizlemede kur düğmesi kapalı ve bileşen özeti türkçe", async () => {
  const request = vi.fn(async (name: string) => {
    if (name === "eklenti.listele") return { ok: true, eklentiler: [], pazarlar: [] };
    return { ok: true, onizleme: { ...onizleme, calistirilabilir: false, hatalar: ["bileşen yok"] } };
  });
  render(<PluginsPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Eklenti kaynağı" }), { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name: "Önizle" }));
  expect(((await screen.findByRole("button", { name: "Kur" })) as HTMLButtonElement).disabled).toBe(true);
  expect(componentSummary(bilesen)).toBe("2 beceri · 1 komut · kanca");
});
