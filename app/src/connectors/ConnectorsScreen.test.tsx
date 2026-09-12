import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ConnectorsScreen } from "./ConnectorsScreen";
import type { ProtocolClient } from "../protocol/client";

// Modül düzeyinde: eskiden yalnız ilk describe'ın içindeydi ve sonraki
// blokların render'ları birikip sorguları çoklu eşleştiriyordu.
afterEach(cleanup);

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
    fireEvent.click(within(dialog).getByRole("button", { name: /Yerel komut/ }));
    const ad = within(dialog).getByLabelText("Ad");
    fireEvent.change(ad, { target: { value: "deneme" } });
    fireEvent.change(within(dialog).getByLabelText("Komut"), { target: { value: "npx test" } });
    const submit = within(dialog).getByRole("button", { name: "Ekle" });
    submit.focus();
    // Sözleşme ODAĞIN KUTUNUN İÇİNDE KALMASI; hangi düğmeye düştüğü değil.
    fireEvent.keyDown(window, { key: "Tab" });
    expect(dialog.contains(document.activeElement)).toBe(true);
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
    fireEvent.click(within(dialog).getByRole("button", { name: /Uzak MCP/ }));
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
    fireEvent.click(within(dialog).getByRole("button", { name: /Uzak MCP/ }));
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
    fireEvent.click(within(dialog).getByRole("button", { name: /Sağlayıcı üzerinden/ }));

    await waitFor(() => expect(client.request).toHaveBeenCalledWith("baglanti.saglayicilar", {}));
    // Hazır olan seçilebilir, olmayan devre dışı.
    const hazir = within(dialog).getByLabelText(/Claude Web/) as HTMLInputElement;
    const hazirDegil = within(dialog).getByLabelText(/ChatGPT Web/) as HTMLInputElement;
    expect(hazir.disabled).toBe(false);
    expect(hazirDegil.disabled).toBe(true);
    // Kullanıcı bu bağlantının neye bağımlı olduğunu görmeli.
    expect(within(dialog).getByText(/connector ekranı açılır/i)).toBeTruthy();
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
    fireEvent.click(within(dialog).getByRole("button", { name: /Sağlayıcı üzerinden/ }));

    await waitFor(() =>
      expect(within(dialog).getByText(/hiçbir web sağlayıcısına bağlı değilsin/i)).toBeTruthy(),
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
    fireEvent.click(within(dialog).getByRole("button", { name: /Sağlayıcı üzerinden/ }));
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
    /* Eskiden burada yeşil bir blok açılıp "şu adresi sağlayıcının MCP alanına
       yapıştır" diyordu — yani kullanıcının az önce YAZDIĞI adresi geri
       veriyordu. Artık panel doğrudan açılır ve doğrulama kendiliğinden
       denenir; kullanıcının ayrıca bir düğmeye basması gerekmez. */
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.panel_ac",
        expect.objectContaining({ saglayici: "claude_web" }),
      ),
    );
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "baglanti.saglayici_dogrula",
        expect.objectContaining({ ad: "Meta Ads" }),
      ),
    );
    expect(screen.queryByRole("button", { name: "Sağlayıcı panelini aç" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Bağlantıyı doğrula" })).toBeNull();
  });

  it("bir işlem sürerken diğer düğmeler kilitlenmez", async () => {
    // Tek bir `busy` bayrağı bütün ekranı kilitliyordu: uzun süren bir istek
    // (ör. sağlayıcı panelini açmak, kullanıcı pencereyi kapatana kadar sürer)
    // boyunca hiçbir düğmeye basılamıyordu ve ekran donmuş görünüyordu.
    let birak: (() => void) | undefined;
    const bekleyen = new Promise<Record<string, unknown>>((resolve) => {
      birak = () => resolve({ ok: true });
    });
    const client = fakeClient(
      [
        { ad: "godot", durum: "bagli", tasima: "stdio", komut: "npx", argumanlar: [] },
        { ad: "meta", durum: "bagli", tasima: "stdio", komut: "npx", argumanlar: [] },
      ],
      { "baglanti.dogrula": bekleyen as unknown as Record<string, unknown> },
    );

    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /^Bağlı/ }));
    const testler = await screen.findAllByRole("button", { name: "Test et" });
    fireEvent.click(testler[0]);
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("baglanti.dogrula", { ad: "godot" }),
    );

    // Kendi düğmesi kilitli, BAŞKA satırınki serbest kalmalı.
    expect((testler[0] as HTMLButtonElement).disabled).toBe(true);
    expect((testler[1] as HTMLButtonElement).disabled).toBe(false);
    birak?.();
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
    fireEvent.click(screen.getByRole("button", { name: /Yerel komut/ }));
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

describe("ConnectorsScreen — silme", () => {
  /* Ölçülmüş hata: her satır için `baglanti.sil` çağrılıyordu. Barındırmalı
     bağlantılar ayrı depoda (`config.hosted_connectors`) yaşar; uç kaydı
     bulamayıp "'X' adlı bağlantı yok" diyor, satır ekranda kalıyor ve
     kullanıcı bağlantıyı silemediğini görüyordu. */
  it("barındırmalı bağlantıyı sağlayıcı ucundan siler", async () => {
    const istekler: { ad: string; veri: unknown }[] = [];
    const client = {
      request: vi.fn(async (ad: string, veri: unknown) => {
        istekler.push({ ad, veri });
        if (ad === "baglanti.listele") {
          return {
            ok: true,
            sunucular: [
              {
                ad: "meta-ads",
                tasima: "hosted",
                url: "https://mcp.facebook.com/ads",
                komut: "",
                argumanlar: [],
                durum: "bagli",
              },
            ],
          };
        }
        return { ok: true };
      }),
    } as unknown as ProtocolClient;

    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(await screen.findByRole("tab", { name: /Bağlı/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Kaldır" }));

    await waitFor(() =>
      expect(istekler.some((istek) => istek.ad === "baglanti.saglayici_sil")).toBe(true),
    );
    expect(istekler.some((istek) => istek.ad === "baglanti.sil")).toBe(false);
  });

  it("yerel MCP sunucusunu normal uçtan siler", async () => {
    const istekler: string[] = [];
    const client = {
      request: vi.fn(async (ad: string) => {
        istekler.push(ad);
        if (ad === "baglanti.listele") {
          return {
            ok: true,
            sunucular: [
              {
                ad: "godot",
                tasima: "stdio",
                komut: "npx",
                argumanlar: ["-y", "godot-mcp"],
                durum: "bagli",
              },
            ],
          };
        }
        return { ok: true };
      }),
    } as unknown as ProtocolClient;

    render(<ConnectorsScreen client={client} onClose={() => undefined} />);
    fireEvent.click(await screen.findByRole("tab", { name: /Bağlı/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Kaldır" }));

    await waitFor(() => expect(istekler).toContain("baglanti.sil"));
    expect(istekler).not.toContain("baglanti.saglayici_sil");
  });
});
