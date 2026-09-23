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
