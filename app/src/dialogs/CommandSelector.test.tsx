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
});
