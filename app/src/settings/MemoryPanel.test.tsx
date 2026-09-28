import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { MemoryPanel } from "./MemoryPanel";

afterEach(cleanup);

it("anıyı ekler, kullanımı kapatır ve tek kaydı kaldırır", async () => {
  let enabled = true;
  let items: { id: string; metin: string }[] = [];
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "bellek.listele") return { ok: true, etkin: enabled, anilar: items };
    if (name === "bellek.ekle") { items = [{ id: "m1", metin: String(data.metin) }]; return { ok: true }; }
    if (name === "bellek.etkinlestir") { enabled = Boolean(data.etkin); return { ok: true }; }
    if (name === "bellek.sil") { items = items.filter((item) => item.id !== data.id); return { ok: true }; }
    return { ok: false };
  });
  render(<MemoryPanel client={{ request } as unknown as ProtocolClient} />);

  await screen.findByText("Henüz kayıtlı anı yok.");
  fireEvent.change(screen.getByRole("textbox", { name: "Yeni anı" }), { target: { value: "Kısa yaz" } });
  fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
  expect(await screen.findByText("Kısa yaz")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox", { name: "Hafızayı kullan" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("bellek.etkinlestir", { etkin: false }));
  fireEvent.click(screen.getByRole("button", { name: "Anıyı kaldır: Kısa yaz" }));
  expect(await screen.findByText("Henüz kayıtlı anı yok.")).toBeTruthy();
});

/* Bkz. bug: "Hafıza okunamadı" hatası GERÇEK sebebi göstermeden çıkıyordu —
   `load()`un catch bloğu sabit bir metinle nedeni örtüyordu; ekranın diğer
   eylemleri (`add`/`remove`/`toggle`) gerçek nedeni zaten gösteriyordu. */
it("gerçek başarısızlık nedenini gösterir ve 'Yeniden dene' isteği tekrarlar", async () => {
  const request = vi.fn(async (name: string) => {
    if (name === "bellek.listele") throw new Error("oturum henüz hazır değil");
    return { ok: false };
  });
  render(<MemoryPanel client={{ request } as unknown as ProtocolClient} />);

  expect(await screen.findByText(/Hafıza okunamadı: oturum henüz hazır değil/)).toBeTruthy();

  request.mockImplementation(async (name: string) =>
    name === "bellek.listele" ? { ok: true, etkin: true, anilar: [] } : { ok: false },
  );
  fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));

  await screen.findByText("Henüz kayıtlı anı yok.");
  expect(screen.queryByText(/Hafıza okunamadı/)).toBeNull();
});
