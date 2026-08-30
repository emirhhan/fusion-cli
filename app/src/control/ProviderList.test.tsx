import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ProviderList } from "./ProviderList";

afterEach(cleanup);

const SATIRLAR = [
  { id: "chatgpt_web", ad: "ChatGPT Web", tur: "web", eylem: "oturum", bagli: false, hesap: "main" },
  { id: "gemini_web", ad: "Gemini Web", tur: "web", eylem: "oturum", bagli: true, hesap: "main" },
  { id: "openrouter", ad: "OpenRouter", tur: "anahtar", eylem: "anahtar", bagli: true, ortam: "OPENROUTER_API_KEY" },
  { id: "openai", ad: "OpenAI", tur: "anahtar", eylem: "anahtar", bagli: false, ortam: "OPENAI_API_KEY" },
];

function client(overrides: Record<string, unknown> = {}) {
  return {
    request: vi.fn(async (name: string) => {
      if (name in overrides) return overrides[name];
      if (name === "saglayici.katalog") return { ok: true, saglayicilar: SATIRLAR };
      if (name === "web.giris") return { ok: true, pid: 7 };
      if (name === "web.giris_durumu") return { ok: true, acik: false };
      if (name === "web.baglan") return { ok: true };
      if (name === "web.dogrula") return { ok: true, gecikme_ms: 120 };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

describe("ProviderList", () => {
  it("kısa satırlar çizer; hiçbirinde açık anahtar kutusu yoktur", async () => {
    render(<ProviderList client={client()} />);
    expect(await screen.findByText("ChatGPT Web")).toBeTruthy();
    expect(screen.getByText("OpenRouter")).toBeTruthy();

    // Kullanıcı uzun uzun input kutuları istemiyor: detay tıklayınca açılır.
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("web sağlayıcısına tıklayınca oturum açma sunar, anahtar sormaz", async () => {
    render(<ProviderList client={client()} />);
    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT Web/ }));

    expect(await screen.findByRole("button", { name: "Oturum aç" })).toBeTruthy();
    expect(screen.queryByLabelText(/API anahtarı/i)).toBeNull();
  });

  it("anahtarlı sağlayıcıya tıklayınca anahtar alanı açılır", async () => {
    render(<ProviderList client={client()} />);
    fireEvent.click(await screen.findByRole("button", { name: /OpenAI/ }));

    expect(await screen.findByLabelText(/API anahtarı/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Oturum aç" })).toBeNull();
  });

  it("bağlı olanı ayırt eder", async () => {
    render(<ProviderList client={client()} />);
    await screen.findByText("Gemini Web");
    expect(screen.getAllByText("bağlı").length).toBe(2);
  });

  it("liste boşsa sessiz kalmaz", async () => {
    // Boş bir kutu, bağlantı hatasıyla "hiç sağlayıcı yok" durumunu ayırt
    // edilemez kılıyordu.
    render(<ProviderList client={client({ "saglayici.katalog": { ok: true, saglayicilar: [] } })} />);
    expect(await screen.findByText(/Sağlayıcı listesi boş/)).toBeTruthy();
  });

  it("arama ile süzülür", async () => {
    render(<ProviderList client={client()} />);
    await screen.findByText("OpenRouter");
    fireEvent.change(screen.getByRole("searchbox", { name: /ara/i }), { target: { value: "gemini" } });

    expect(screen.queryByText("OpenRouter")).toBeNull();
    expect(screen.getByText("Gemini Web")).toBeTruthy();
  });
});

describe("ProviderList — web oturumu", () => {
  it("giriş penceresi kapanınca oturumu kaydeder ve gerçekten sınar", async () => {
    // Eskiden yalnız liste tazeleniyordu: profil klasörü oluştuğu için "bağlı"
    // görünüyor, Fusion ise sağlayıcıyı hiç kullanamıyordu.
    const fake = client();
    render(<ProviderList client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT Web/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Oturum aç" }));

    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("web.baglan", {
      saglayici: "chatgpt_web",
      hesap: "main",
    }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("web.dogrula", {
      saglayici: "chatgpt_web",
      hesap: "main",
    }));
  });

  it("sınama geçmezse bunu açıkça söyler", async () => {
    const fake = client({ "web.dogrula": { ok: false, metin: "Oturum cevap vermedi" } });
    render(<ProviderList client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT Web/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Oturum aç" }));

    expect(await screen.findByText(/sınama geçmedi/i)).toBeTruthy();
  });

  it("bağlı sağlayıcıda sınama ve çıkış sunar", async () => {
    const fake = client();
    render(<ProviderList client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: /Gemini Web/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Çıkış yap" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("web.cikis", {
      saglayici: "gemini_web",
      hesap: "main",
    }));
  });

  it("profil var ama oturum kayıtlı değilse uyarır", async () => {
    const fake = client({
      "saglayici.katalog": {
        ok: true,
        saglayicilar: [
          { id: "chatgpt_web", ad: "ChatGPT Web", tur: "web", eylem: "oturum", bagli: false, profil_var: true, hesap: "main" },
        ],
      },
    });
    render(<ProviderList client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT Web/ }));

    expect(await screen.findByText(/giriş yarım kalmış olabilir/i)).toBeTruthy();
  });
});

