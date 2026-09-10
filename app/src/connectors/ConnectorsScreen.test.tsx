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
