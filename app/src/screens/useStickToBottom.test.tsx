/** Sohbetin en altta kalması — ama okumayı bölmeden.
 *
 * Ölçülen hata: `Conversation` hiç kaydırma kodu taşımıyordu; cevaplar görünür
 * alanın altında kalıyor, kullanıcı cevap gelmediğini sanıyordu.
 */
import { cleanup, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { PIN_THRESHOLD_PX, enAlttaMi, useStickToBottom } from "./useStickToBottom";

afterEach(cleanup);

describe("enAlttaMi", () => {
  it("tam alttayken doğru", () => {
    expect(enAlttaMi({ scrollHeight: 1000, scrollTop: 600, clientHeight: 400 })).toBe(true);
  });

  it("eşik içindeyken doğru — birkaç piksel yukarısı okuma sayılmaz", () => {
    expect(
      enAlttaMi({ scrollHeight: 1000, scrollTop: 600 - PIN_THRESHOLD_PX, clientHeight: 400 }),
    ).toBe(true);
  });

  it("geçmişi okurken yanlış", () => {
    expect(enAlttaMi({ scrollHeight: 5000, scrollTop: 100, clientHeight: 400 })).toBe(false);
  });
});

/** Kaydırma kutusunu elle yöneten sahte bileşen: jsdom yerleşim hesaplamaz. */
function Sahne({ mesajlar, gonderdi }: { mesajlar: string[]; gonderdi: boolean }) {
  const kutu = useRef<HTMLDivElement>(null);
  const icerik = useRef<HTMLDivElement>(null);
  useStickToBottom(kutu, icerik, mesajlar, gonderdi);
  return (
    <div data-testid="kutu" ref={kutu}>
      <div ref={icerik}>{mesajlar.map((m) => <p key={m}>{m}</p>)}</div>
    </div>
  );
}

function olcuVer(el: HTMLElement, scrollHeight: number, clientHeight: number) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: clientHeight });
}

describe("useStickToBottom", () => {
  it("en alttayken yeni mesajda en altta kalır", () => {
    const { getByTestId, rerender } = render(<Sahne gonderdi={false} mesajlar={["a"]} />);
    const kutu = getByTestId("kutu");
    olcuVer(kutu, 2000, 400);
    rerender(<Sahne gonderdi={false} mesajlar={["a", "b"]} />);
    expect(kutu.scrollTop).toBe(2000);
  });

  it("kullanıcı yukarı kaydırıp okurken ZORLA aşağı çekmez", () => {
    const { getByTestId, rerender } = render(<Sahne gonderdi={false} mesajlar={["a"]} />);
    const kutu = getByTestId("kutu");
    olcuVer(kutu, 5000, 400);
    // Kullanıcı geçmişe çıktı.
    kutu.scrollTop = 100;
    kutu.dispatchEvent(new Event("scroll"));
    rerender(<Sahne gonderdi={false} mesajlar={["a", "b"]} />);
    expect(kutu.scrollTop).toBe(100);
  });

  it("kullanıcı mesaj gönderdiğinde okurken bile en alta iner", () => {
    const { getByTestId, rerender } = render(<Sahne gonderdi={false} mesajlar={["a"]} />);
    const kutu = getByTestId("kutu");
    olcuVer(kutu, 5000, 400);
    kutu.scrollTop = 100;
    kutu.dispatchEvent(new Event("scroll"));
    rerender(<Sahne gonderdi mesajlar={["a", "benim mesajım"]} />);
    expect(kutu.scrollTop).toBe(5000);
  });
});
