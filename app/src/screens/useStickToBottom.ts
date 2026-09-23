import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";

/** Alttan bu kadar yakınsa kullanıcı "en altta" sayılır (piksel).
 *
 *  Tam sıfır istenmez: alt kenar boşluğu, yuvarlama ve son satırın yarım
 *  görünmesi kullanıcıyı birkaç piksel yukarıda bırakabilir; bu, okuduğu
 *  geçmişe çıktığı anlamına gelmez. Bir satır yüksekliğinin birkaç katı. */
export const PIN_THRESHOLD_PX = 80;

/** Kaydırma kutusu en altta mı? Saf; doğrudan test edilir. */
export function enAlttaMi(
  kutu: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">,
  esik: number = PIN_THRESHOLD_PX,
): boolean {
  return kutu.scrollHeight - kutu.scrollTop - kutu.clientHeight <= esik;
}

/**
 * Sohbeti en altta tut — ama kullanıcının okumasını bölme.
 *
 * Ölçüldü (23 Eylül, kurulu uygulama): `Conversation` hiç kaydırma kodu
 * taşımıyordu. Uzun bir cevaptan sonra yeni mesajlar görünür alanın altında
 * kalıyordu; kullanıcı cevap gelmediğini sanıyordu. Dökümde cevap VARDI
 * ("Desktop'ta kaç .md var?" → "3"), ekranda yoktu.
 *
 * Kurallar (Claude'un davranışı):
 * 1. Kullanıcı en alttaysa, yeni içerik gelince en altta kalır.
 * 2. Kullanıcı yukarı kaydırıp geçmişi okuyorsa zorla aşağı çekilmez.
 * 3. Kullanıcı mesaj gönderdiğinde HER ZAMAN en alta inilir.
 * 4. İçerik sonradan büyürse (görsel yüklenir, markdown çizilir) ve kullanıcı
 *    en alttaysa yine en altta kalır.
 */
export function useStickToBottom<T>(
  kutuRef: RefObject<HTMLElement | null>,
  icerikRef: RefObject<HTMLElement | null>,
  bagimlilik: T,
  kullaniciGonderdi: boolean,
): () => void {
  const sabitRef = useRef(true);

  const enAltaIn = useCallback(() => {
    const kutu = kutuRef.current;
    if (!kutu) return;
    // CSS `scroll-behavior: smooth` burada İSTENMEZ: akış sırasında saniyede
    // birçok güncelleme gelir; yumuşak kaydırma hedefin gerisinde kalır ve
    // animasyonun ortasında `onScroll` kullanıcıyı "yukarıda" sanıp sabitlemeyi
    // bırakırdı.
    if (typeof kutu.scrollTo === "function") {
      kutu.scrollTo({ top: kutu.scrollHeight, behavior: "instant" });
    } else {
      // `scrollTo` olmayan ortam (eski WebView, jsdom): doğrudan konum yaz.
      kutu.scrollTop = kutu.scrollHeight;
    }
    sabitRef.current = true;
  }, [kutuRef]);

  const kaydirildi = useCallback(() => {
    const kutu = kutuRef.current;
    if (kutu) sabitRef.current = enAlttaMi(kutu);
  }, [kutuRef]);

  // Kural 1 ve 3: mesaj listesi değişince.
  useLayoutEffect(() => {
    if (sabitRef.current || kullaniciGonderdi) enAltaIn();
  }, [bagimlilik, kullaniciGonderdi, enAltaIn]);

  // Kaydırma dinleyicisi ve Kural 4: içerik sonradan büyürse.
  useLayoutEffect(() => {
    const kutu = kutuRef.current;
    const icerik = icerikRef.current;
    if (!kutu) return;
    kutu.addEventListener("scroll", kaydirildi, { passive: true });
    const gozlemci =
      typeof ResizeObserver === "undefined" || !icerik
        ? null
        : new ResizeObserver(() => { if (sabitRef.current) enAltaIn(); });
    if (icerik) gozlemci?.observe(icerik);
    return () => {
      kutu.removeEventListener("scroll", kaydirildi);
      gozlemci?.disconnect();
    };
  }, [kutuRef, icerikRef, kaydirildi, enAltaIn]);

  return enAltaIn;
}
