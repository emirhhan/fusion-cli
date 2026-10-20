import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Conversation, type Mesaj } from "./Conversation";

afterEach(cleanup);

/**
 * Büyük konuşma performansı — yayın kapısının ölçülebilir maddesi.
 *
 * Amaç mikro-optimizasyon yarıştırmak değil, mesaj sayısı büyüdüğünde arayüzün
 * kilitlenmediğini kanıtlamak. Paylaşımlı Intel CI çalıştırıcısında aynı kodun
 * 1519 ms ölçülmesi, 1500 ms eşiğinin zamanlayıcı yüküne karşı kırılgan
 * olduğunu gösterdi. 2500 ms bütçe büyük gerilemeleri yakalamaya devam ederken
 * ortak çalıştırıcının makul zamanlama payını da kapsar.
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
    expect(elapsed).toBeLessThan(2500);
  });
});
