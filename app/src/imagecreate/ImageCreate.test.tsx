import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImageCreate } from "./ImageCreate";

afterEach(cleanup);

function istemci(olustur: () => Promise<Record<string, unknown>>) {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "gorsel.saglayicilar") {
        return { ok: true, secenekler: [{ deger: "gemini_web/main", etiket: "Gemini" }, { deger: "chatgpt_web/main", etiket: "ChatGPT" }] };
      }
      return olustur();
    }),
  };
}

describe("ImageCreate", () => {
  it("istemi seçili sağlayıcıyla gönderir ve üretilen görseli listeler", async () => {
    const client = istemci(async () => ({
      ok: true, saglayici: "Gemini",
      dosyalar: [{ yol: "/Users/u/Pictures/Fusion/a.png", genislik: 1024, yukseklik: 559 }],
    }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} reveal={vi.fn()} />);

    await screen.findByRole("option", { name: "ChatGPT" });
    fireEvent.change(screen.getByLabelText("Görsel istemi"), { target: { value: "kırmızı kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));

    const gorsel = await screen.findByRole("img", { name: "kırmızı kask" });
    expect(gorsel.getAttribute("src")).toBe("asset:///Users/u/Pictures/Fusion/a.png");
    expect(client.request).toHaveBeenCalledWith("gorsel.olustur", { istem: "kırmızı kask", saglayici: "gemini_web/main" });
  });

  it("hata metnini gösterir ve düğmeyi yeniden açar", async () => {
    const client = istemci(async () => ({ ok: false, metin: "Gemini insan doğrulaması istiyor." }));
    render(<ImageCreate client={client} toUrl={() => null} reveal={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Görsel istemi"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));

    expect((await screen.findByRole("alert")).textContent).toContain("insan doğrulaması");
    await waitFor(() => expect((screen.getByRole("button", { name: "Oluştur" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("örnek isteme tıklayınca kutuya yazar", async () => {
    render(<ImageCreate client={istemci(async () => ({ ok: true }))} toUrl={() => null} reveal={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /kırmızı motosiklet kaskı/ }));
    expect((screen.getByLabelText("Görsel istemi") as HTMLTextAreaElement).value).toContain("kırmızı motosiklet kaskı");
  });
});
