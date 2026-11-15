import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { AutoMemoryPanel } from "./AutoMemoryPanel";

afterEach(cleanup);

function durum(metin: string, etkin = true) {
  const satir = metin ? metin.split("\n").length : 0;
  return { ok: true, etkin, metin, dosya: "/tmp/bellek/BELLEK.md", satir, bayt: metin.length, kirpildi: false, konular: metin ? ["odeme"] : [], sinir_satir: 200 };
}

it("belleği gösterir, düzenlemeyi kaydeder ve kapatır", async () => {
  let metin = "# Bellek\n- kısa yanıt";
  let etkin = true;
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "otobellek.durum") return durum(metin, etkin);
    if (name === "otobellek.kaydet") { metin = String(data.metin); return durum(metin, etkin); }
    if (name === "otobellek.etkinlestir") { etkin = Boolean(data.etkin); return durum(etkin ? metin : "", etkin); }
    return { ok: false, metin: "bilinmeyen" };
  });
  render(<AutoMemoryPanel client={{ request } as unknown as ProtocolClient} />);

  const alan = await screen.findByRole("textbox", { name: "Bellek metni" });
  expect((alan as HTMLTextAreaElement).value).toBe("# Bellek\n- kısa yanıt");
  expect(screen.getByTestId("auto-memory-status").textContent).toContain("ilk 2 satır yüklendi");
  expect(screen.getByTestId("auto-memory-status").textContent).toContain("konular: odeme");

  const kaydet = screen.getByRole("button", { name: "Belleği kaydet" }) as HTMLButtonElement;
  expect(kaydet.disabled).toBe(true);
  fireEvent.change(alan, { target: { value: "# Bellek\n- kısa yanıt\n- HPOS aktif" } });
  fireEvent.click(kaydet);
  await waitFor(() => expect(request).toHaveBeenCalledWith("otobellek.kaydet", { metin: "# Bellek\n- kısa yanıt\n- HPOS aktif" }));
  expect(await screen.findByText("Bellek kaydedildi.")).toBeTruthy();

  fireEvent.click(screen.getByRole("checkbox", { name: "Otomatik belleği kullan" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("otobellek.etkinlestir", { etkin: false }));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Bellek metni" })).toBeNull());
});

it("içe aktarma isteğini gönderir ve okuma hatasını nedeniyle gösterir", async () => {
  const request = vi.fn(async (name: string) => {
    if (name === "otobellek.durum") return durum("");
    if (name === "otobellek.ice_aktar") return { ...durum("- Claude notu"), alinan: 1 };
    return { ok: false };
  });
  render(<AutoMemoryPanel client={{ request } as unknown as ProtocolClient} />);
  expect(await screen.findByText("Bellek henüz boş.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Claude'dan içe aktar" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("otobellek.ice_aktar", { kaynak: "claude" }));
  expect(await screen.findByText("Claude belleği içe aktarıldı.")).toBeTruthy();

  cleanup();
  const kirik = vi.fn(async () => { throw new Error("oturum hazır değil"); });
  render(<AutoMemoryPanel client={{ request: kirik } as unknown as ProtocolClient} />);
  expect(await screen.findByText(/Bellek okunamadı: oturum hazır değil/)).toBeTruthy();
});
