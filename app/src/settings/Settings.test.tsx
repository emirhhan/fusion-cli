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
        sunucular: [{ ad: "github", komut: "npx", argumanlar: ["-y", "mcp-github"], tasima: "stdio", durum: "bagli", arac_sayisi: 3 }],
      };
      if (name === "web.saglayicilar") return {
        ok: true,
        saglayicilar: [{ id: "claude_web", ad: "Claude Web", bagli: true }],
      };
      if (name === "kullanim.durum") return {
        ok: true,
        kullanim: {
          cagri: 0,
          girdi_token: 0,
          cikti_token: 0,
          toplam_token: 0,
          maliyet_usd: 0,
          modeller: [],
        },
        saglik: [],
      };
      if (name === "ses.durum") return {
        ok: true,
        ayar: { hiz: 1, model: null, robotik: 0.5 },
        kullanilabilir: true,
        model_kurulu: false,
        motor: "sistem",
        ses: "Cem",
        turkce: true,
        yukseltme: null,
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
    expect(await screen.findByText("Sistem · Cem")).toBeTruthy();
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
    expect(screen.queryByLabelText("Ad")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Bağlantı ekle" }));
    expect(screen.getByRole("dialog", { name: "MCP bağlantısı ekle" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "dosyalar" } });
    fireEvent.change(screen.getByLabelText("Komut"), { target: { value: "npx -y mcp-fs" } });
    fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kaydet" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.ekle", {
      ad: "dosyalar",
      komut: "npx -y mcp-fs",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("ayar MCP popup'ı Escape ile kapanır ve odağı geri verir", async () => {
    render(<Settings client={client()} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    const open = await screen.findByRole("button", { name: "Bağlantı ekle" });
    open.focus();
    fireEvent.click(open);
    const dialog = screen.getByRole("dialog", { name: "MCP bağlantısı ekle" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(open);
  });
  it("bekleyen eklemede Escape odağı döndürür ve ikinci popup açılmaz", async () => {
    const base = client();
    let finish!: (value: Record<string, unknown>) => void;
    const request = (name: string, data: Record<string, unknown>) => name === "baglanti.ekle"
      ? new Promise<Record<string, unknown>>((resolve) => { finish = resolve; })
      : base.request(name, data);
    render(<Settings client={{ request } as unknown as ProtocolClient} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    const open = await screen.findByRole("button", { name: "Bağlantı ekle" });
    open.focus();
    fireEvent.click(open);
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "yerel" } });
    fireEvent.change(screen.getByLabelText("Komut"), { target: { value: "npx server" } });
    fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kaydet" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.activeElement).toBe(open);
    fireEvent.click(open);
    expect(screen.queryByRole("dialog")).toBeNull();
    finish({ ok: true });
    await waitFor(() => expect(open.getAttribute("aria-disabled")).toBe("false"));
  });

  it("iki alan dolmadan bağlantı eklenemez", async () => {
    render(<Settings client={client()} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    await screen.findByText("github");
    fireEvent.click(screen.getByRole("button", { name: "Bağlantı ekle" }));
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "dosyalar" } });

    expect((screen.getByRole("button", { name: "Bağlantıyı kaydet" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("bağlantıyı kaldırır", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    fireEvent.click(await screen.findByRole("button", { name: "github bağlantısını kaldır" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.sil", { ad: "github" }));
  });

  it("uzak MCP ekler ve OAuth giriş durumunu gösterir", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);
    await screen.findByText("github");
    fireEvent.click(screen.getByRole("button", { name: "Bağlantı ekle" }));

    fireEvent.change(screen.getByLabelText("Bağlantı türü"), { target: { value: "streamable_http" } });
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "meta" } });
    fireEvent.change(screen.getByLabelText("MCP adresi"), { target: { value: "https://mcp.example.com/mcp" } });
    fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kaydet" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.ekle", {
      ad: "meta",
      tasima: "streamable_http",
      url: "https://mcp.example.com/mcp",
      kapsamlar: "",
      client_id: "",
    }));
  });

  it("bağlı MCP için araç sayısı ve test eylemi gösterir", async () => {
    const fake = client();
    render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" />);

    expect(await screen.findByText("3 araç")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "github bağlantısını test et" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("baglanti.dogrula", { ad: "github" }));
  });
});
