import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Computer } from "./Computer";

afterEach(cleanup);

function client(overrides: Record<string, unknown> = {}) {
  const calls: { name: string; data: Record<string, unknown> }[] = [];
  const ayarlar: Record<string, unknown> = {
    enabled: true, denied_apps: [], background: true, unhide_on_finish: true, escape_stops: true, ...overrides,
  };
  return {
    calls,
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      calls.push({ name, data });
      if (name === "bilgisayar.uygulamalar") return { ok: true, uygulamalar: ["Mail", "Notes"] };
      if (name === "bilgisayar.ayar_yaz") {
        ayarlar[data.anahtar as string] = data.deger;
        return { ok: true, ayarlar: { ...ayarlar }, metin: `desktop.${String(data.anahtar)} kaydedildi` };
      }
      return { ok: true, ayarlar: { ...ayarlar } };
    }),
  };
}

describe("Bu bilgisayar ayarları", () => {
  it("anahtar kapatılınca desktop.enabled yazılır", async () => {
    const api = client();
    render(<Computer client={api} />);
    const toggle = await screen.findByRole("switch", { name: "Computer use'u etkinleştir" });

    fireEvent.click(toggle);

    await waitFor(() => expect(api.calls.some((c) => c.name === "bilgisayar.ayar_yaz" && c.data.anahtar === "enabled" && c.data.deger === false)).toBe(true));
    expect(screen.getByText("desktop.enabled kaydedildi")).toBeTruthy();
  });

  it("varsayılan kapalı okunur (#420)", async () => {
    const api = client({ enabled: undefined });
    render(<Computer client={api} />);
    const toggle = await screen.findByRole("switch", { name: "Computer use'u etkinleştir" });
    expect((toggle as HTMLInputElement).checked).toBe(false);
  });

  it("reddedilen uygulama eklenip kaldırılır", async () => {
    const api = client({ denied_apps: ["Notes"] });
    render(<Computer client={api} />);
    fireEvent.change(await screen.findByLabelText("Uygulama ekle"), { target: { value: "Mail" } });
    fireEvent.click(screen.getByRole("button", { name: "Reddet" }));
    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "denied_apps" && JSON.stringify(c.data.deger) === '["Notes","Mail"]')).toBe(true));

    fireEvent.click(screen.getAllByRole("button", { name: "Kaldır" })[0]);
    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "denied_apps" && JSON.stringify(c.data.deger) === '["Mail"]')).toBe(true));
  });

  it("kademeler sabit tablo olarak gösterilir, değiştirilecek denetim yok (#424)", async () => {
    render(<Computer client={client()} />);
    const table = await screen.findByRole("table", { name: "Uygulama kademeleri" });
    expect(table.textContent).toContain("yatırım platformları");
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByLabelText("Kademe")).toBeNull();
  });

  it("yazma hatası kullanıcıya gösterilir", async () => {
    const api = client();
    api.request.mockImplementation(async (name: string) => {
      if (name === "bilgisayar.ayar_yaz") return { ok: false, metin: "desktop.escape_stops: hata" };
      if (name === "bilgisayar.uygulamalar") return { ok: true, uygulamalar: [] };
      return { ok: true, ayarlar: { enabled: true } };
    });
    render(<Computer client={api} />);
    fireEvent.click(await screen.findByRole("switch", { name: "Esc ile durdur" }));

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "desktop.escape_stops: hata");
  });
});
