import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ConnectorsScreen } from "./ConnectorsScreen";
import type { ProtocolClient } from "../protocol/client";

interface RpcRow {
  ad: string;
  argumanlar?: string[];
  arac_sayisi?: number;
  durum?: string;
  komut?: string;
  tasima?: string;
  url?: string;
}

/** Sahte protokol istemcisi: baglanti.listele için verilen satırları döndürür,
 *  diğer çağrıları kaydeder. */
function fakeClient(
  rows: RpcRow[] = [],
  responses: Record<string, Record<string, unknown>> = {},
) {
  const request = vi.fn(async (name: string, _data: unknown) => {
    if (name === "baglanti.listele") return { ok: true, sunucular: rows };
    if (responses[name]) return responses[name];
    return { ok: true, metin: "tamam" };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

describe("ConnectorsScreen", () => {
  afterEach(cleanup);
  it("özel bağlantı popup'ı odağı alır ve Escape ile açan düğmeye döner", async () => {
    render(<ConnectorsScreen client={fakeClient()} onClose={() => undefined} />);
    const add = screen.getByRole("button", { name: "Ekle" });
    add.focus();
    fireEvent.click(add);
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(add);
  });
  it("popup odağı içeride tutar ve başarısız eklemede girdileri korur", async () => {
    render(<ConnectorsScreen client={fakeClient([], { "baglanti.ekle": { ok: false, metin: "Sunucuya ulaşılamadı" } })} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    const ad = within(dialog).getByLabelText("Ad");
    fireEvent.change(ad, { target: { value: "deneme" } });
    fireEvent.change(within(dialog).getByLabelText("Komut"), { target: { value: "npx test" } });
    const submit = within(dialog).getByRole("button", { name: "Ekle" });
    submit.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Özel sunucu formunu kapat" }));
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(submit);
    fireEvent.click(submit);
    await within(dialog).findByText("Sunucuya ulaşılamadı");
    expect(ad).toHaveProperty("value", "deneme");
  });
  it("otomatik kaydı reddeden uzak sunucu için client_id girilebilir", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    fireEvent.change(within(dialog).getByLabelText("Tür"), { target: { value: "streamable_http" } });
    fireEvent.change(within(dialog).getByLabelText("Ad"), { target: { value: "Meta Ads" } });
    fireEvent.change(within(dialog).getByLabelText("MCP adresi"), {
      target: { value: "https://mcp.facebook.com/ads" },
    });
    fireEvent.change(within(dialog).getByLabelText("Client ID"), { target: { value: "123456" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Ekle" }));
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.ekle",
        expect.objectContaining({ client_id: "123456", tasima: "streamable_http" }),
      ),
    );
  });

  it("uzak sunucuya OAuth yerine erişim token'ı ile bağlanılabilir", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    fireEvent.change(within(dialog).getByLabelText("Tür"), { target: { value: "streamable_http" } });
    fireEvent.change(within(dialog).getByLabelText("Ad"), { target: { value: "Meta Ads" } });
    fireEvent.change(within(dialog).getByLabelText("MCP adresi"), {
      target: { value: "https://mcp.facebook.com/ads" },
    });
    fireEvent.change(within(dialog).getByLabelText("Erişim token'ı"), {
      target: { value: "gizli-token" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Ekle" }));
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.ekle",
        expect.objectContaining({ token: "gizli-token", tasima: "streamable_http" }),
      ),
    );
  });

  it("sağlayıcı üzerinden bağlantıda hazır sağlayıcıyı seçtirir ve uyarısını gösterir", async () => {
    const client = fakeClient([], {
      "baglanti.saglayicilar": {
        ok: true,
        saglayicilar: [
          { id: "claude_web", ad: "Claude Web", adres: "https://claude.ai/settings/connectors", hazir: true },
          { id: "chatgpt_web", ad: "ChatGPT Web", adres: "https://chatgpt.com/#settings/Connectors", hazir: false },
        ],
      },
    });
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    fireEvent.change(within(dialog).getByLabelText("Tür"), { target: { value: "hosted" } });

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.saglayicilar", {}));
    // Hazır olan seçilebilir, olmayan devre dışı.
    const hazir = within(dialog).getByLabelText(/Claude Web/) as HTMLInputElement;
    const hazirDegil = within(dialog).getByLabelText(/ChatGPT Web/) as HTMLInputElement;
    expect(hazir.disabled).toBe(false);
    expect(hazirDegil.disabled).toBe(true);
    // Kullanıcı bu bağlantının neye bağımlı olduğunu görmeli.
    expect(within(dialog).getByText(/yalnızca giriş yaptığınız model bağlıyken/i)).toBeTruthy();
  });

  it("hiç web sağlayıcısı bağlı değilse uyarır ve eklemeye izin vermez", async () => {
    const client = fakeClient([], {
      "baglanti.saglayicilar": {
        ok: true,
        saglayicilar: [
          { id: "claude_web", ad: "Claude Web", adres: "https://claude.ai/settings/connectors", hazir: false },
        ],
      },
    });
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    fireEvent.change(within(dialog).getByLabelText("Tür"), { target: { value: "hosted" } });

    await waitFor(() =>
      expect(within(dialog).getByText(/hiçbir web sağlayıcısına bağlı değilsiniz/i)).toBeTruthy(),
    );
    expect(
      (within(dialog).getByRole("button", { name: "Ekle" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("sağlayıcı bağlantısını ekler ve panelini açar", async () => {
    const client = fakeClient([], {
      "baglanti.saglayicilar": {
        ok: true,
        saglayicilar: [
          { id: "claude_web", ad: "Claude Web", adres: "https://claude.ai/settings/connectors", hazir: true },
        ],
      },
      "baglanti.saglayici_ekle": {
        ok: true,
        ad: "Meta Ads",
        mcp_adresi: "https://mcp.facebook.com/ads",
        adres: "https://claude.ai/settings/connectors",
        saglayici: "claude_web",
      },
    });
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    const dialog = screen.getByRole("dialog", { name: "Özel MCP sunucusu ekle" });
    fireEvent.change(within(dialog).getByLabelText("Tür"), { target: { value: "hosted" } });
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.saglayicilar", {}));
    fireEvent.change(within(dialog).getByLabelText("Ad"), { target: { value: "Meta Ads" } });
    fireEvent.change(within(dialog).getByLabelText("MCP adresi"), {
      target: { value: "https://mcp.facebook.com/ads" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Ekle" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.saglayici_ekle",
        expect.objectContaining({ ad: "Meta Ads", saglayici: "claude_web" }),
      ),
    );
    // Ekleme sonrası kullanıcıya yapıştıracağı adres ve paneli açan düğme verilir.
    const panel = await screen.findByRole("button", { name: "Sağlayıcı panelini aç" });
    fireEvent.click(panel);
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.panel_ac",
        expect.objectContaining({ saglayici: "claude_web" }),
      ),
    );
  });

  it("keşfet sekmesinde 3 banner ve katalog tablosunu gösterir", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.listele", {}));

    const banners = screen.getByLabelText("Popüler bağlantılar");
    // Banner içinde tam 3 "Bağlan" düğmesi olmalı.
    expect(within(banners).getAllByRole("button", { name: "Bağlan" })).toHaveLength(3);
    // Katalog tablosunda bilinen bir sunucu görünür.
    expect(screen.getByText("Notion")).toBeTruthy();
  });

  it("stdio katalog girişini komutla ekler", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    // Shopify banner'ı stdio; Bağlan komutu doğru payload'la baglanti.ekle çağırır.
    const banners = screen.getByLabelText("Popüler bağlantılar");
    const shopify = within(banners).getByText("Shopify").closest("article")!;
    fireEvent.click(within(shopify).getByRole("button", { name: "Bağlan" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "shopify",
        komut: "npx -y @shopify/dev-mcp@latest",
      }),
    );
  });

  it("klasör isteyen katalog girişini kurulum formundan argümanla ekler", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Bağlantı ara"), { target: { value: "dosya sistemi" } });
    const row = screen.getByText("Dosya sistemi").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Kur" }));
    const setup = screen.getByLabelText("Dosya sistemi kurulumu");
    fireEvent.change(within(setup).getByLabelText("İzin verilen klasör"), {
      target: { value: "/Users/demo/Proje" },
    });
    fireEvent.click(within(setup).getByRole("button", { name: "Bağlantıyı ekle" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "filesystem",
        komut: "npx -y @modelcontextprotocol/server-filesystem",
        argumanlar: ["/Users/demo/Proje"],
      }),
    );
  });

  it("API anahtarını komuta katmadan şifreli ortam payloadıyla gönderir", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Bağlantı ara"), { target: { value: "brave" } });
    const row = screen.getByText("Brave Search").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Kur" }));
    const setup = screen.getByLabelText("Brave Search kurulumu");
    const secret = within(setup).getByLabelText("Brave API anahtarı");
    expect(secret).toHaveProperty("type", "password");
    fireEvent.change(secret, { target: { value: "brave-gizli" } });
    fireEvent.click(within(setup).getByRole("button", { name: "Bağlantıyı ekle" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "brave-search",
        komut: "npx -y @modelcontextprotocol/server-brave-search",
        ortam: { BRAVE_API_KEY: "brave-gizli" },
      }),
    );
  });

  it("PostgreSQL parolasını yapılandırma argümanına açık yazmaz", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Bağlantı ara"), { target: { value: "postgres" } });
    const row = screen.getByText("PostgreSQL").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Kur" }));
    const setup = screen.getByLabelText("PostgreSQL kurulumu");
    fireEvent.change(within(setup).getByLabelText("PostgreSQL bağlantı adresi"), {
      target: { value: "postgresql://user:secret@localhost/db" },
    });
    fireEvent.click(within(setup).getByRole("button", { name: "Bağlantıyı ekle" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "postgres",
        komut: "npx -y @modelcontextprotocol/server-postgres",
        argumanlar: ["__FUSION_SECRET__:POSTGRES_URL"],
        ortam: { POSTGRES_URL: "postgresql://user:secret@localhost/db" },
      }),
    );
  });

  it("uzak OAuth katalog girişinde backendin başlattığı girişi tekrarlamaz", async () => {
    const client = fakeClient([], {
      "baglanti.ekle": { ok: true, durum: "giris_bekleniyor" },
    });
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    // `baglanti.ekle` remote bağlantıda OAuth'u backend tarafında başlatır.
    const banners = screen.getByLabelText("Popüler bağlantılar");
    const github = within(banners).getByText("GitHub").closest("article")!;
    fireEvent.click(within(github).getByRole("button", { name: "Bağlan" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "github",
        tasima: "streamable_http",
        url: "https://api.githubcopilot.com/mcp/",
        kapsamlar: "",
        client_id: "",
      }),
    );
    expect(client.request).not.toHaveBeenCalledWith("baglanti.giris", { ad: "github" });
  });

  it("önceden eklenmiş uzak bağlantının girişini başlatır", async () => {
    const client = fakeClient([
      {
        ad: "github",
        durum: "yapilandirildi",
        tasima: "streamable_http",
        url: "https://api.githubcopilot.com/mcp/",
      },
    ]);
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.listele", {}));

    const banners = screen.getByLabelText("Popüler bağlantılar");
    const github = within(banners).getByText("GitHub").closest("article")!;
    fireEvent.click(within(github).getByRole("button", { name: "Bağlan" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.giris", { ad: "github" }),
    );
    expect(client.request).not.toHaveBeenCalledWith(
      "baglanti.ekle",
      expect.objectContaining({ ad: "github" }),
    );
  });

  it("bağlı sunucu için banner'da 'Bağlı' gösterir ve tekrar eklemez", async () => {
    const client = fakeClient([{ ad: "github", durum: "bagli", arac_sayisi: 12 }]);
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.listele", {}));

    const banners = screen.getByLabelText("Popüler bağlantılar");
    const github = within(banners).getByText("GitHub").closest("article")!;
    const button = within(github).getByRole("button", { name: "Bağlı" });
    expect(button).toBeTruthy();
    expect(button).toHaveProperty("disabled", true);
  });

  it("arama katalog tablosunu filtreler ve banner'ı gizler", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Bağlantı ara"), { target: { value: "linear" } });

    expect(screen.queryByLabelText("Popüler bağlantılar")).toBeNull();
    expect(screen.getByText("Linear")).toBeTruthy();
    expect(screen.queryByText("Notion")).toBeNull();
  });

  it("özel sunucu formundan stdio bağlantı ekler", async () => {
    const client = fakeClient();
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    fireEvent.change(screen.getByLabelText("Ad"), { target: { value: "godot" } });
    fireEvent.change(screen.getByLabelText("Komut"), { target: { value: "npx -y godot-mcp" } });
    const form = screen.getByLabelText("Özel MCP sunucusu ekle");
    fireEvent.click(within(form).getByRole("button", { name: "Ekle" }));

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.ekle", {
        ad: "godot",
        komut: "npx -y godot-mcp",
      }),
    );
  });

  it("bağlı sekmesi bağlı sunucuları ve araç sayısını listeler", async () => {
    const client = fakeClient([{ ad: "github", durum: "bagli", arac_sayisi: 8, tasima: "streamable_http", url: "https://api.githubcopilot.com/mcp" }]);
    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.listele", {}));

    fireEvent.click(screen.getByRole("tab", { name: /^Bağlı/ }));
    const connected = screen.getByLabelText("Bağlı sunucular");
    expect(within(connected).getByText("GitHub")).toBeTruthy();
    expect(within(connected).getByText("8 araç")).toBeTruthy();
  });
});
