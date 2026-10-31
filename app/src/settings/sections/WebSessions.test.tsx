import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { WebSessions, domainSummary } from "./WebSessions";

const GIZLI = "cerez-degeri-GIZLI-91";

const profil = {
  ad: "is",
  alan_adlari: ["example.com", "shop.example.org"],
  onayli_alan_adlari: ["example.com"],
  cerez_sayisi: 2,
  kaynak: "dosya",
  ice_aktarma: 1_700_000_000,
  son_kullanim: null,
};

function fakeClient(overrides: Record<string, unknown> = {}) {
  const calls: [string, Record<string, unknown>][] = [];
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    calls.push([name, data]);
    if (name === "tarayici.profiller") return { ok: true, profiller: [profil], varsayilan: "", anahtar_var: true, etkin: true, ...overrides };
    if (name === "tarayici.dosya_onizle") return { ok: true, alan_adlari: ["example.com", "other.net"], cerez_sayisi: 3 };
    if (name === "tarayici.ice_aktar") return { ok: true, metin: "'yeni' profili yazıldı." };
    if (name === "tarayici.sil") return { ok: true, metin: "'is' silindi." };
    if (name === "tarayici.varsayilan") return { ok: true, varsayilan: String(data.ad) };
    return { ok: true };
  });
  return { client: { request } as unknown as ProtocolClient, request, calls };
}

describe("WebSessions", () => {
  afterEach(cleanup);

  it("profilleri alan adı ve sayıyla listeler, çerez değeri göstermez", async () => {
    const { client } = fakeClient();
    render(<WebSessions client={client} />);

    expect(await screen.findByText("is")).toBeTruthy();
    expect(screen.getByText(/example.com, shop.example.org · 2 çerez · Dosyadan/)).toBeTruthy();
    expect(screen.getByText(/Onaylı siteler: example.com/)).toBeTruthy();
    expect(document.body.textContent).not.toContain(GIZLI);
  });

  it("dosya içe aktarma önce alan adlarını gösterir, seçilenlerle onaylı aktarır", async () => {
    const { client, request } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.change(screen.getByLabelText("Profil adı"), { target: { value: "yeni" } });
    fireEvent.change(screen.getByLabelText("Çerez dosyası"), { target: { value: "/tmp/cookies.txt" } });
    fireEvent.click(screen.getByRole("button", { name: "Alan adlarını göster" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.dosya_onizle", { yol: "/tmp/cookies.txt" }));
    // Hiçbir alan adı hazır işaretli gelmez: seçimsiz içe aktarma kapalıdır.
    expect(await screen.findByLabelText("other.net")).toHaveProperty("checked", false);
    expect(screen.getByRole("button", { name: "İçe aktar" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("example.com"));
    fireEvent.click(screen.getByRole("button", { name: "İçe aktar" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("tarayici.ice_aktar", { ad: "yeni", alan_adlari: ["example.com"], yol: "/tmp/cookies.txt" }),
    );
    expect(await screen.findByText("'yeni' profili yazıldı.")).toBeTruthy();
  });

  it("silme iki adımlıdır: ilk tık onay ister, ikinci tık siler", async () => {
    const { client, request } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.click(screen.getByRole("button", { name: "Sil" }));
    expect(request).not.toHaveBeenCalledWith("tarayici.sil", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Evet, sil" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.sil", { ad: "is" }));
  });

  it("varsayılan yap isteği gönderir ve rozet gösterir", async () => {
    const { client, request } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.click(screen.getByRole("button", { name: "Varsayılan yap" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.varsayilan", { ad: "is" }));
  });

  it("şifreleme anahtarı yoksa uyarır ve içe aktarmayı kapatır", async () => {
    const { client } = fakeClient({ anahtar_var: false, metin: "Şifreleme anahtarı yok." });
    render(<WebSessions client={client} />);

    expect((await screen.findByRole("alert")).textContent).toContain("Şifreleme anahtarı yok.");
    expect(screen.getByLabelText("Profil adı")).toHaveProperty("disabled", true);
  });

  it("giriş penceresi yalnız http(s) adresiyle açılır", async () => {
    const { client, request } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.click(screen.getByRole("button", { name: "Giriş penceresi aç" }));
    const input = screen.getByLabelText("is için giriş adresi");
    fireEvent.change(input, { target: { value: "ftp://x" } });
    expect(screen.getByRole("button", { name: "Pencereyi aç" })).toHaveProperty("disabled", true);
    fireEvent.change(input, { target: { value: "https://example.com/login" } });
    fireEvent.click(screen.getByRole("button", { name: "Pencereyi aç" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.giris", { ad: "is", url: "https://example.com/login" }));
  });
});

describe("WebSessions — ayarlar ve yeni profil girişi", () => {
  afterEach(cleanup);

  it("'Hepsini seç' tüm alan adlarını işaretler, 'Temizle' kaldırır", async () => {
    const { client } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");
    fireEvent.change(screen.getByLabelText("Çerez dosyası"), { target: { value: "/tmp/c.txt" } });
    fireEvent.click(screen.getByRole("button", { name: "Alan adlarını göster" }));
    await screen.findByLabelText("other.net");

    fireEvent.click(screen.getByRole("button", { name: "Hepsini seç" }));
    expect(screen.getByLabelText("other.net")).toHaveProperty("checked", true);
    fireEvent.click(screen.getByRole("button", { name: "Temizle" }));
    expect(screen.getByLabelText("other.net")).toHaveProperty("checked", false);
  });

  it("profil kapısı ve pencere kipi anahtarları tarayici.ayar gönderir", async () => {
    const { client, request } = fakeClient({ headless: true, etkin: true });
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.click(screen.getByLabelText(/profiles_enabled/));
    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.ayar", { anahtar: "profiles_enabled", deger: false }));
    fireEvent.click(screen.getByLabelText(/görünür açılsın/));
    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.ayar", { anahtar: "headless", deger: false }));
  });

  it("Tarayıcı paneli paylaşımı (browser.panel_agent) kalıcı ayar olarak yazılır", async () => {
    const { client, request } = fakeClient({ panel_ajan: true });
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    const kutu = screen.getByLabelText(/panel_agent/);
    expect(kutu).toHaveProperty("checked", true);
    fireEvent.click(kutu);

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.ayar", { anahtar: "panel_agent", deger: false }));
  });

  it("yeni profil için giriş penceresi ad ister ve tarayici.giris'e adı gönderir", async () => {
    const { client, request } = fakeClient();
    render(<WebSessions client={client} />);
    await screen.findByText("is");

    fireEvent.click(screen.getByRole("button", { name: "Yeni profil için giriş…" }));
    const url = screen.getByLabelText("Giriş adresi");
    fireEvent.change(url, { target: { value: "https://example.com/login" } });
    expect(screen.getByRole("button", { name: "Pencereyi aç" })).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByLabelText("Yeni profil adı"), { target: { value: "../kacis" } });
    expect(screen.getByRole("button", { name: "Pencereyi aç" })).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByLabelText("Yeni profil adı"), { target: { value: "yeni-hesap" } });
    fireEvent.click(screen.getByRole("button", { name: "Pencereyi aç" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("tarayici.giris", { ad: "yeni-hesap", url: "https://example.com/login" }));
  });

  it("giriş penceresi hata ile kapanırsa sebep hata satırında görünür", async () => {
    // Yoklama zamanlayıcısı anında tetiklenir: gerçek 2 sn beklenmez.
    const interval = vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
      window.setTimeout(handler, 0);
      return 1;
    }) as typeof window.setInterval);
    try {
      const { client } = fakeClient();
      (client.request as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (name: string) => {
        if (name === "tarayici.profiller") return { ok: true, profiller: [profil], varsayilan: "", anahtar_var: true, etkin: true };
        if (name === "tarayici.giris") return { ok: true, pid: 7 };
        if (name === "tarayici.giris_durumu") return { ok: false, acik: false, metin: "Chrome giriş penceresi hata ile kapandı: playwright install chromium" };
        return { ok: true };
      });
      render(<WebSessions client={client} />);
      await screen.findByText("is");
      fireEvent.click(screen.getByRole("button", { name: "Giriş penceresi aç" }));
      fireEvent.change(screen.getByLabelText("is için giriş adresi"), { target: { value: "https://example.com" } });
      fireEvent.click(screen.getByRole("button", { name: "Pencereyi aç" }));

      expect((await screen.findByRole("alert")).textContent).toContain("playwright install chromium");
    } finally {
      interval.mockRestore();
    }
  });
});

describe("domainSummary", () => {
  it("dördünden fazlasını +N ile kısaltır", () => {
    expect(domainSummary(["a", "b"])).toBe("a, b");
    expect(domainSummary(["a", "b", "c", "d", "e", "f"])).toBe("a, b, c, d +2");
  });
});
