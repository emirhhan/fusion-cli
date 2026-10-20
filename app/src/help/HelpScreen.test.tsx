import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { HelpScreen } from "./HelpScreen";

const kokDizin = dirname(fileURLToPath(import.meta.url));

afterEach(cleanup);

describe("HelpScreen", () => {
  /* Bkz. bug: yardım paneli ekrana sığmıyordu ve kaydırılamıyordu (ebeveyn
     kutu `overflow: hidden` taşıyor — Shell.css). Kök öğe kendi kaydırmasını
     açmalı: `main.help` kaydırılabilir tek DOM köküdür. */
  test("kök öğe kendi taşmasında kaydırılabilir (overflow-y açık)", () => {
    const { container } = render(<HelpScreen onClose={vi.fn()} />);
    const kok = container.querySelector("main.help");
    expect(kok).toBeTruthy();

    // jsdom gerçek düzen hesaplamaz; CSS dosyasının METNİ regresyona karşı
    // korunur (bkz. `notify/notification.zindex.test.ts`ile aynı desen).
    const css = readFileSync(join(kokDizin, "help.css"), "utf-8");
    expect(css).toMatch(/\.help\s*{[^}]*overflow-y:\s*auto/s);
    expect(css).toMatch(/\.help\s*{[^}]*height:\s*100%/s);
  });

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
