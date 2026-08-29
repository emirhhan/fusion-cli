import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { WebProviders } from "./WebProviders";

afterEach(cleanup);

const KARTLAR = [
  { id: "chatgpt_web", ad: "ChatGPT Web (Plus/Pro)", hesap: "main", anahtar_gerekir: false, bagli: false, arac_destegi: "none", olcum_gecti: false, etkin: false },
  { id: "claude_web", ad: "Claude Web", hesap: "main", anahtar_gerekir: false, bagli: true, arac_destegi: "emulated", olcum_gecti: true, etkin: true },
  { id: "gemini_web", ad: "Gemini Web", hesap: "main", anahtar_gerekir: false, bagli: false, arac_destegi: "none", olcum_gecti: false, etkin: false },
  { id: "copilot_web", ad: "Copilot Web", hesap: "main", anahtar_gerekir: false, bagli: false, arac_destegi: "none", olcum_gecti: false, etkin: false },
];

function client(overrides: Record<string, unknown> = {}) {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "web.saglayicilar") return { ok: true, saglayicilar: KARTLAR };
      if (name === "web.giris") return { ok: true, pid: 4242 };
      if (name === "web.giris_durumu") return { ok: true, acik: false };
      return { ok: true, ...overrides };
    }),
  } as unknown as ProtocolClient;
}

describe("WebProviders", () => {
  it("dört sağlayıcıyı gösterir ve HİÇBİRİNE anahtar kutusu çizmez", async () => {
    render(<WebProviders client={client()} />);

    expect(await screen.findByText("ChatGPT Web (Plus/Pro)")).toBeTruthy();
    expect(screen.getByText("Claude Web")).toBeTruthy();
    expect(screen.getByText("Gemini Web")).toBeTruthy();
    expect(screen.getByText("Copilot Web")).toBeTruthy();

    // Bu sağlayıcılar abonelikle çalışır: anahtar GİRİŞİ olmamalı. Metnin
    // "anahtar gerekmez" demesi doğrudur ve kalmalı; yasak olan kutudur.
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByPlaceholderText(/anahtar/i)).toBeNull();
    expect(document.body.textContent).toMatch(/anahtarı gerekmez/i);
  });

  it("bağlı olanı ve olmayanı ayırt eder", async () => {
    render(<WebProviders client={client()} />);
    await screen.findByText("Claude Web");

    expect(screen.getAllByRole("button", { name: "Giriş yap" }).length).toBe(3);
    expect(screen.getByRole("button", { name: "Bağlantıyı yenile" })).toBeTruthy();
  });

  it("giriş penceresini açar ve kapanınca durumu kendiliğinden tazeler", async () => {
    const fake = client();
    render(<WebProviders client={fake} />);
    await screen.findByText("Gemini Web");

    fireEvent.click(screen.getAllByRole("button", { name: "Giriş yap" })[1]);

    await waitFor(() => {
      expect(fake.request).toHaveBeenCalledWith("web.giris", { saglayici: "gemini_web", hesap: "main" });
    });
    // Pencere kapandığında liste yeniden okunur; kullanıcı çerez kopyalamaz.
    await waitFor(() => {
      expect(fake.request).toHaveBeenCalledWith("web.giris_durumu", { pid: 4242 });
    });
  });

  it("protokol hatasında sessiz kalmaz", async () => {
    const kirik = {
      request: vi.fn(async () => ({ ok: false, metin: "Tarayıcı açılamadı." })),
    } as unknown as ProtocolClient;

    render(<WebProviders client={kirik} />);

    expect(await screen.findByText("Tarayıcı açılamadı.")).toBeTruthy();
  });
});
