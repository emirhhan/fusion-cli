import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Settings } from "./Settings";

function client() {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "kontrol.durum") return {
        ok: true,
        kok: "/Users/test/Fusion",
        gateway: { durum: "calisiyor", adres: "http://127.0.0.1:8787/v1" },
        saglayicilar: [{ id: "openrouter", ad: "OpenRouter", kurulu: true }],
        mcp: [{ ad: "github", komut: "npx" }],
      };
      if (name === "web.saglayicilar") return {
        ok: true,
        saglayicilar: [{ id: "claude_web", ad: "Claude Web", bagli: true }],
      };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

// Depodaki diğer testlerle aynı: render'lar birikirse sorgular çoklu eşleşir.
afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Settings", () => {
  it("tema ve yerel tercihleri kontrol panelinden ayrı gösterir", async () => {
    const onThemeChange = vi.fn();
    render(<Settings client={client()} onClose={() => undefined} onThemeChange={onThemeChange} themePreference="system" />);
    expect(await screen.findByRole("heading", { name: "Ayarlar" })).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Görünüm" }), { target: { value: "dark" } });
    expect(onThemeChange).toHaveBeenCalledWith("dark");

    const history = screen.getByRole("checkbox", { name: "Geçmiş bölümünü açık başlat" }) as HTMLInputElement;
    expect(history.checked).toBe(true);
    fireEvent.click(history);
    expect(localStorage.getItem("fusion.sidebar.history-open.v1")).toBe("false");
  });

  it("bağlantı, çalışma alanı ve gizlilik özetini gerçek protokolden yükler", async () => {
    render(<Settings client={client()} onClose={() => undefined} onThemeChange={() => undefined} themePreference="light" />);
    await waitFor(() => expect(screen.getByText("/Users/test/Fusion")).toBeTruthy());
    expect(screen.getByText("2 bağlı bağlantı")).toBeTruthy();
    expect(screen.getByText("Gateway çalışıyor")).toBeTruthy();
    expect(screen.getByText(/verileriniz bu cihazda/i)).toBeTruthy();
  });
});
