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
    fireEvent.click(await screen.findByLabelText("other.net"));
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

describe("domainSummary", () => {
  it("dördünden fazlasını +N ile kısaltır", () => {
    expect(domainSummary(["a", "b"])).toBe("a, b");
    expect(domainSummary(["a", "b", "c", "d", "e", "f"])).toBe("a, b, c, d +2");
  });
});
