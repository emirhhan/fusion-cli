import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

function client() {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "saglayici.katalog") return { ok: true, saglayicilar: SATIRLAR };
      if (name === "web.giris") return { ok: true, pid: 7 };
      if (name === "web.giris_durumu") return { ok: true, acik: false };
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

  it("arama ile süzülür", async () => {
    render(<ProviderList client={client()} />);
    await screen.findByText("OpenRouter");
    fireEvent.change(screen.getByRole("searchbox", { name: /ara/i }), { target: { value: "gemini" } });

    expect(screen.queryByText("OpenRouter")).toBeNull();
    expect(screen.getByText("Gemini Web")).toBeTruthy();
  });
});
