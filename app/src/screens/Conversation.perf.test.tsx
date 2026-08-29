import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Conversation, type Mesaj } from "./Conversation";

afterEach(cleanup);

/**
 * Büyük konuşma performansı — yayın kapısının ölçülebilir maddesi.
 *
 * Eşik cömert tutuldu (1500 ms): amaç mikro-optimizasyon yarıştırmak değil,
 * mesaj sayısı büyüdüğünde arayüzün kilitlenmediğini kanıtlamak. Eşiği geçen
 * bir değişiklik gerçek bir gerileme demektir; makine yavaşlığı bu farkı
 * üretmez (ölçülen değer tipik olarak bunun onda biri kadardır).
 */
describe("Conversation — büyük konuşma", () => {
  it("800 mesajı kabul edilebilir sürede çizer", () => {
    const mesajlar: Mesaj[] = Array.from({ length: 800 }, (_, index) => ({
      metin: `Mesaj ${index}: ${"içerik ".repeat(12)}`,
      rol: index % 3 === 0 ? "kullanici" : index % 3 === 1 ? "asistan" : "olay",
    }));

    const started = performance.now();
    render(<Conversation mesajlar={mesajlar} />);
    const elapsed = performance.now() - started;

    expect(screen.getAllByLabelText("Fusion yanıtı").length).toBeGreaterThan(200);
    expect(elapsed).toBeLessThan(1500);
  });
});
