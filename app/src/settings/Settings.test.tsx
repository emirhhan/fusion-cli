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
      if (name === "ayar.talimat") return { ok: true, metin: "Kısa yaz.", sinir: 4000 };
      if (name === "baglanti.listele") return {
        ok: true,
        sunucular: [{ ad: "github", komut: "npx", argumanlar: ["-y", "mcp-github"] }],
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

describe("Settings — derinlik", () => {
  it("kalıcı talimatı yükler ve kaydeder", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    const alan = (await screen.findByLabelText("Kalıcı talimat")) as HTMLTextAreaElement;
    expect(alan.value).toBe("Kısa yaz.");

    // Değişiklik yokken kaydetmek anlamsız: düğme kapalı.
    expect((screen.getByRole("button", { name: "Kaydet" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(alan, { target: { value: "Cevapları kısa tut." } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("ayar.talimat_kaydet", {
      metin: "Cevapları kısa tut.",
    }));
  });

  it("MCP bağlantılarını listeler ve ekler", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    expect(await screen.findByText("github")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "dosyalar" } });
    fireEvent.change(screen.getByLabelText("Komut"), { target: { value: "npx -y mcp-fs" } });
    fireEvent.click(screen.getByRole("button", { name: "Bağlantı ekle" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.ekle", {
      ad: "dosyalar",
      komut: "npx -y mcp-fs",
    }));
  });

  it("iki alan dolmadan bağlantı eklenemez", async () => {
    render(<Settings client={client()} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    await screen.findByText("github");
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "dosyalar" } });

    expect((screen.getByRole("button", { name: "Bağlantı ekle" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("bağlantıyı kaldırır", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    fireEvent.click(await screen.findByRole("button", { name: "github bağlantısını kaldır" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.sil", { ad: "github" }));
  });
});

