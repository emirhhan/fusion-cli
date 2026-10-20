import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Notification, insanDogrulamasiGerekiyor } from "./Notification";

afterEach(cleanup);

describe("insanDogrulamasiGerekiyor", () => {
  /* İşaret çekirdeğin KENDİ mesajından okunur; arayüz kendi kalıbını
     uydurmaz (bkz. `_human_verification_message`). */
  test("çekirdeğin doğrulama mesajını tanır", () => {
    const cekirdek =
      "authentication: ChatGPT Web insan doğrulaması (captcha) istiyor. " +
      "Bunu otomatik aşmak mümkün değil";

    expect(insanDogrulamasiGerekiyor(cekirdek)).toBe(true);
  });

  test("sıradan cevabı doğrulama sanmaz", () => {
    expect(insanDogrulamasiGerekiyor("Dosyayı yazdım ve testler geçti.")).toBe(false);
    expect(insanDogrulamasiGerekiyor("")).toBe(false);
  });
});

describe("Notification", () => {
  test("başlığı, metni ve eylemi gösterir", () => {
    const onSelect = vi.fn();
    render(
      <Notification
        baslik="Sağlayıcı doğrulama istiyor"
        eylem={{ etiket: "Giriş penceresini aç", onSelect }}
        metin="Bunu ancak sen tamamlayabilirsin."
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain("Sağlayıcı doğrulama istiyor");
    fireEvent.click(screen.getByRole("button", { name: "Giriş penceresini aç" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  test("eylem verilmezse yalnız kapatma sunulur", () => {
    render(<Notification baslik="Bilgi" metin="Kısa not." onDismiss={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Bildirimi kapat" })).toBeTruthy();
  });

  test("Escape kartı kapatır", () => {
    const onDismiss = vi.fn();
    render(<Notification baslik="Bilgi" metin="Kısa not." onDismiss={onDismiss} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  /* Eylem gerektiren bir bildirim kullanıcı görmeden kaybolursa hiç
     gösterilmemiş sayılır; kart kendiliğinden kapanmaz. */
  test("kendiliğinden kapanmaz", () => {
    vi.useFakeTimers();
    try {
      const onDismiss = vi.fn();
      render(<Notification baslik="Bilgi" metin="Kısa not." onDismiss={onDismiss} />);

      vi.advanceTimersByTime(60_000);

      expect(onDismiss).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
