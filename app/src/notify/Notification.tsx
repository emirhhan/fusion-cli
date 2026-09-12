import { useEffect } from "react";
import "./notification.css";

/**
 * Bildirim kartı — macOS bildirim merkezindeki gibi, sağ üstte.
 *
 * Neden var: bazı durumlarda Fusion tek başına ilerleyemez ve kullanıcının
 * BİR ŞEY YAPMASI gerekir — sağlayıcı insan doğrulaması (captcha) istediğinde
 * ya da oturum düştüğünde. Bu, sohbetin içine gömülmüş bir hata satırı olarak
 * kayboluyordu; kullanıcı neden durduğunu anlamıyordu.
 *
 * Kart KENDİLİĞİNDEN KAPANMAZ. Eylem gerektiren bir bildirim, kullanıcı onu
 * görmeden önce kaybolursa hiç gösterilmemiş sayılır.
 */

export interface NotificationProps {
  baslik: string;
  metin: string;
  /** Varsa tek bir eylem düğmesi; yoksa yalnız kapatma sunulur. */
  eylem?: { etiket: string; onSelect: () => void };
  onDismiss: () => void;
}

export function Notification({ baslik, metin, eylem, onDismiss }: NotificationProps) {
  useEffect(() => {
    const kacis = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", kacis);
    return () => document.removeEventListener("keydown", kacis);
  }, [onDismiss]);

  return (
    <div aria-live="assertive" className="notification" role="alert">
      <div className="notification__body">
        <strong>{baslik}</strong>
        <p>{metin}</p>
      </div>
      <div className="notification__actions">
        {eylem && (
          <button className="notification__primary" onClick={eylem.onSelect} type="button">
            {eylem.etiket}
          </button>
        )}
        <button aria-label="Bildirimi kapat" className="notification__close" onClick={onDismiss} type="button">
          Kapat
        </button>
      </div>
    </div>
  );
}

/** Sağlayıcının insan doğrulaması istediğini söyleyen çekirdek işareti. */
const DOGRULAMA_ISARETI = "insan doğrulaması";

/**
 * Çekirdekten gelen metin, kullanıcı eylemi gerektiren bir duvar mı?
 *
 * İşaret çekirdeğin KENDİ mesajından okunur; arayüz kendi kalıbını uydurmaz.
 */
export function insanDogrulamasiGerekiyor(metin: string): boolean {
  return metin.includes(DOGRULAMA_ISARETI);
}
