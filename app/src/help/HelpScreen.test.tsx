import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { HelpScreen } from "./HelpScreen";

afterEach(cleanup);

describe("HelpScreen", () => {
  test("kısayolları tuş ve anlamıyla listeler", () => {
    render(<HelpScreen onClose={vi.fn()} />);

    expect(screen.getByText("Shift + Tab")).toBeTruthy();
    expect(screen.getByText(/İzin modunu değiştir/)).toBeTruthy();
  });

  /* Eskiden "Yardım" menüsü Dersler ekranını açıyordu: iki menü öğesi aynı yere
     gidiyor, kullanıcı aradığını bulamıyordu. Burası aranan şeyi vermeli. */
  test("sık sorulanlar kapalı başlar, tıklayınca cevabı açar", () => {
    render(<HelpScreen onClose={vi.fn()} />);

    const soru = screen.getByText("Parolamı unuttum, ne olacak?");
    expect(soru.closest("details")?.hasAttribute("open")).toBe(false);

    fireEvent.click(soru);

    expect(screen.getByText(/kurtarma kodunu/i)).toBeTruthy();
  });

  test("sunucu olmadığını ve kurtarma kodunun tek yol olduğunu söyler", () => {
    render(<HelpScreen onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Parolamı unuttum, ne olacak?"));

    expect(screen.getByText(/sunucu yok/i)).toBeTruthy();
  });

  test("sürüm verilmişse gösterilir", () => {
    render(<HelpScreen onClose={vi.fn()} surum="0.4.0" />);

    expect(screen.getByText("Sürüm 0.4.0")).toBeTruthy();
  });

  test("sürüm yoksa boş satır çizilmez", () => {
    const { container } = render(<HelpScreen onClose={vi.fn()} />);

    expect(container.querySelector(".help__version")).toBeNull();
  });

  test("ayarlara gitme yolu sunar", () => {
    const onOpenSettings = vi.fn();
    render(<HelpScreen onClose={vi.fn()} onOpenSettings={onOpenSettings} />);

    fireEvent.click(screen.getByRole("button", { name: /Ayarlar'ı aç/ }));

    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });

  test("kapatma isteği iletilir", () => {
    const onClose = vi.fn();
    render(<HelpScreen onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
