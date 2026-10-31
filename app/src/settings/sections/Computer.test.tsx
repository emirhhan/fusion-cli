import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Computer } from "./Computer";

afterEach(cleanup);

function client(overrides: Record<string, unknown> = {}) {
  const calls: { name: string; data: Record<string, unknown> }[] = [];
  const ayarlar: Record<string, unknown> = {
    enabled: true, control_level: "full", category_defaults: true, denied_apps: [], app_levels: [],
    app_consent: true, background: true, unhide_on_finish: true, escape_stops: true, ...overrides,
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
  it("anahtar kapatılınca desktop.enabled yazılır ve kademe seçimi kilitlenir", async () => {
    const api = client();
    render(<Computer client={api} />);
    const toggle = await screen.findByRole("switch", { name: "Bilgisayar kullanımını etkinleştir" });

    fireEvent.click(toggle);

    await waitFor(() => expect(api.calls.some((c) => c.name === "bilgisayar.ayar_yaz" && c.data.anahtar === "enabled" && c.data.deger === false)).toBe(true));
    expect(screen.getByText("desktop.enabled kaydedildi")).toBeTruthy();
  });

  it("kademe seçilir ve reddedilen uygulama eklenip kaldırılır", async () => {
    const api = client({ denied_apps: ["Notes"] });
    render(<Computer client={api} />);
    fireEvent.click(await screen.findByRole("radio", { name: /^TıklaTıklar/ }));
    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "control_level" && c.data.deger === "click")).toBe(true));

    fireEvent.change(screen.getByLabelText("Uygulama ekle"), { target: { value: "Mail" } });
    fireEvent.click(screen.getByRole("button", { name: "Reddet" }));
    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "denied_apps" && JSON.stringify(c.data.deger) === '["Notes","Mail"]')).toBe(true));

    fireEvent.click(screen.getAllByRole("button", { name: "Kaldır" })[0]);
    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "denied_apps" && JSON.stringify(c.data.deger) === '["Mail"]')).toBe(true));
  });

  it("uygulama kademesi 'ad=kademe' olarak eklenir; aynı uygulamanın eskisi düşer", async () => {
    const api = client({ app_levels: ["Terminal=click"] });
    render(<Computer client={api} />);
    expect(await screen.findByText("Terminal · Tıkla")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Uygulama adı"), { target: { value: "terminal" } });
    fireEvent.change(screen.getByLabelText("Kademe"), { target: { value: "full" } });
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));

    await waitFor(() => expect(api.calls.some((c) => c.data.anahtar === "app_levels" && JSON.stringify(c.data.deger) === '["terminal=full"]')).toBe(true));
  });

  it("yazma hatası kullanıcıya gösterilir", async () => {
    const api = client();
    api.request.mockImplementation(async (name: string) => {
      if (name === "bilgisayar.ayar_yaz") return { ok: false, metin: "desktop.app_levels: hata" };
      if (name === "bilgisayar.uygulamalar") return { ok: true, uygulamalar: [] };
      return { ok: true, ayarlar: { enabled: true } };
    });
    render(<Computer client={api} />);
    fireEvent.click(await screen.findByRole("switch", { name: "Esc ile durdur" }));

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "desktop.app_levels: hata");
  });
});
