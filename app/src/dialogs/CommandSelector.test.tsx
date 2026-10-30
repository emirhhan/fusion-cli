import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandSelector, type CommandSelectorPayload } from "./CommandSelector";

const selector: CommandSelectorPayload = {
  adim: "model",
  tur: "secim",
  baslik: "Bir model seç",
  secenekler: [
    { deger: "agent openai/gpt", etiket: "Agent", aciklama: "Ana çalışma modeli" },
    { deger: "judge openai/gpt", etiket: "Hakem", aciklama: "Doğrulama modeli" },
  ],
  devam: { komut: "model", arguman_on_eki: "" },
  serbest_metin: null,
};

describe("CommandSelector", () => {
  it("seçimi komut devamı olarak döndürür", () => {
    const onSelect = vi.fn();
    render(<CommandSelector busy={false} onCancel={() => undefined} onSelect={onSelect} open selector={selector} />);
    fireEvent.click(screen.getByRole("button", { name: /Agent/ }));
    expect(onSelect).toHaveBeenCalledWith("/model agent openai/gpt");
  });

  it("gizli metni parola alanında toplar ve boş değeri göndermez", () => {
    const onSelect = vi.fn();
    render(<CommandSelector
      busy={false}
      onCancel={() => undefined}
      onSelect={onSelect}
      open
      selector={{
        ...selector,
        tur: "gizli_metin",
        secenekler: [],
        devam: { komut: "providers", arguman_on_eki: "add openai " },
        serbest_metin: { gizli: true, yer_tutucu: "API anahtarı" },
      }}
    />);
    const input = screen.getByPlaceholderText("API anahtarı");
    expect(input.getAttribute("type")).toBe("password");
    expect((screen.getByRole("button", { name: "Devam et" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(input, { target: { value: "secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Devam et" }));
    expect(onSelect).toHaveBeenCalledWith("/providers add openai secret-value");
  });

  // Ölçüldü (30 Ekim): busy değişince efekt yeniden kuruluyor, hata sonrası yazılan token siliniyordu (U4-12).
  it("gönder → hata → tekrar akışında yazılan gizli değer silinmez (U4-12)", () => {
    const gizli = { ...selector, tur: "gizli_metin" as const, secenekler: [], devam: { komut: "providers", arguman_on_eki: "add x " }, serbest_metin: { gizli: true, yer_tutucu: "Anahtar" } };
    const onCancel = () => undefined;
    const view = render(<CommandSelector busy={false} onCancel={onCancel} onSelect={vi.fn()} open selector={gizli} />);
    const input = screen.getByPlaceholderText("Anahtar") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "tok-123" } });
    view.rerender(<CommandSelector busy onCancel={onCancel} onSelect={vi.fn()} open selector={gizli} />);
    view.rerender(<CommandSelector busy={false} error="Reddedildi" onCancel={onCancel} onSelect={vi.fn()} open selector={gizli} />);
    expect((screen.getByPlaceholderText("Anahtar") as HTMLInputElement).value).toBe("tok-123");
  });
});
