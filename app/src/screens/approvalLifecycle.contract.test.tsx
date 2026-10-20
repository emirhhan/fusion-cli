import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Approval } from "../dialogs/Approval";

const approval = {
  tur: "onay" as const,
  arac: "offline_server__resource_update",
  baslik: "Bu hedef değiştirilsin mi?",
  hedef: "kaynak-a",
  secenekler: [
    { deger: "once", etiket: "Evet" },
    { deger: "deny", etiket: "Hayır" },
  ],
};

const question = {
  tur: "soru" as const,
  soru: "Birinci projenin adı ne olsun?",
  secenekler: [{ etiket: "Örnek" }],
};

afterEach(cleanup);

describe("Onay kartı yaşam döngüsü sözleşmesi", () => {
  it("yanıt beklenirken tıklama ve klavye aynı kararı iki kez göndermez", () => {
    const onCevap = vi.fn(() => new Promise<void>(() => undefined));
    render(<Approval soru={approval} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: "Evet" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "1" });
    expect(onCevap).toHaveBeenCalledTimes(1);
  });

  it("yanıt beklenirken karar düğmelerini devre dışı bırakır", () => {
    render(<Approval soru={approval} onCevap={() => new Promise<void>(() => undefined)} />);
    fireEvent.click(screen.getByRole("button", { name: "Evet" }));
    expect((screen.getByRole("button", { name: "Evet" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Hayır" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("ardışık soruya geçince eski serbest cevabı yeni soruya taşımaz", () => {
    const onCevap = vi.fn();
    const view = render(<Approval soru={question} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Diğer/ }));
    fireEvent.change(screen.getByLabelText("Cevabın"), { target: { value: "Eski proje" } });
    view.rerender(<Approval soru={{ tur: "soru", soru: "İkinci projenin adı ne olsun?" }} onCevap={onCevap} />);
    expect((screen.getByLabelText("Cevabın") as HTMLInputElement).value).toBe("");
    fireEvent.submit(screen.getByLabelText("Cevabın").closest("form")!);
    expect(onCevap).not.toHaveBeenCalled();
  });

  it("serbest cevap kapalıysa sayı tuşu gizli Diğer seçeneğini açmaz", () => {
    render(<Approval soru={question} serbestCevap={false} onCevap={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "2" });
    expect(screen.queryByLabelText("Cevabın")).toBeNull();
  });

  it("normal soru seçimini mevcut metin envelope ile bildirir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={question} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Örnek/ }));
    expect(onCevap).toHaveBeenCalledWith({ metin: "Örnek" });
  });
});

it("gönderim hatasında kartı korur ve yeniden denemeye izin verir", async () => {
  const onCevap = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(undefined);
  render(<Approval soru={approval} onCevap={onCevap} />);
  fireEvent.click(screen.getByRole("button", { name: "Evet" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Evet" }));
  expect(onCevap).toHaveBeenCalledTimes(2);
});

it("kart kapanınca odağı önceki girişe geri verir", () => {
  const input = document.createElement("input");
  document.body.append(input);
  input.focus();
  const view = render(<Approval soru={approval} onCevap={vi.fn()} />);
  expect(document.activeElement).toBe(screen.getByRole("dialog"));
  view.unmount();
  expect(document.activeElement).toBe(input);
  input.remove();
});
