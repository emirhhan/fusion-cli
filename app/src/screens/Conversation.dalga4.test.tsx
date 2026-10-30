import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Conversation, type Mesaj } from "./Conversation";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Conversation — dalga 4 P2/P3", () => {
  it("aynı metinli iki görev maddesi de çizilir (U1-27)", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const mesajlar: Mesaj[] = [{
      id: "g", rol: "gorevler", metin: "Görevler",
      gorevler: [{ durum: "bitti", metin: "Test et" }, { durum: "bekliyor", metin: "Test et" }],
    }];
    render(<Conversation mesajlar={mesajlar} running={false} />);
    expect(screen.getAllByText("Test et")).toHaveLength(2);
    expect(errors.mock.calls.flat().join(" ")).not.toContain("same key");
    errors.mockRestore();
  });

  it("'Hata:' ile başlayan meşru yanıt hata sayılmaz, bayrak hata sayar (U1-28)", () => {
    render(<Conversation running={false} onHataBildir={vi.fn()} mesajlar={[
      { id: "a", rol: "asistan", metin: "Hata: bu bir örnek açıklama" },
    ]} />);
    expect(screen.queryByRole("button", { name: "Hatayı bildir" })).toBeNull();
  });

  it("çalışma süresi saati de yazar (U1-34)", () => {
    const { container } = render(<Conversation running={false} mesajlar={[
      { id: "u", rol: "kullanici", metin: "x" },
      { id: "e", rol: "olay", metin: "o", baslangicZamani: 0, adimlar: [{ metin: "o", arac: "read_file", durum: "ok" }] },
      { id: "a", rol: "asistan", metin: "bitti", bitisZamani: 3700_000 },
    ]} />);
    expect(container.querySelector("summary")?.textContent).toBe("1sa 1d 40sn çalıştı");
  });

  it("ara anlatım görsel kartını kaldırmaz, nihai yanıt kaldırır (U1-23)", () => {
    const u: Mesaj = { id: "u", rol: "kullanici", metin: "/görsel mavi kuş" };
    const { rerender } = render(<Conversation running mesajlar={[u, { id: "n", rol: "asistan", metin: "Başlıyorum", ara: true }]} />);
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).not.toBeNull();
    rerender(<Conversation running mesajlar={[u, { id: "a", rol: "asistan", metin: "hazır" }]} />);
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).toBeNull();
  });

  it("'Kopyalandı' durumu birkaç saniye sonra silinir (U1-35)", async () => {
    vi.useFakeTimers();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<Conversation running={false} mesajlar={[{ id: "a", rol: "asistan", metin: "Sonuç" }]} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Yanıtı kopyala" })); });
    expect(screen.getByText("Kopyalandı")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(4500); });
    expect(screen.queryByText("Kopyalandı")).toBeNull();
  });
});
