import { useEffect, useRef } from "react";
import "./CloseConfirm.css";

/**
 * `fusion://yeni?kok=…` onayı (P-064).
 *
 * Ölçüldü (31 Ekim): dış bağlantı sormadan o klasörü kök alan bir kod sohbeti açıyordu;
 * kullanıcı alışkanlıkla görev yazarsa ajan beklenmedik bir klasörde çalışırdı. Normal
 * akışta klasörü kullanıcı seçer; bağlantıdan gelen kök de onun onayından geçer.
 * Görsel dil kapatma onayıyla aynıdır (aynı stil sınıfları).
 */
export function DeepLinkConfirm({
  kok,
  onCancel,
  onConfirm,
}: {
  kok: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const onCancelRef = useRef(onCancel);
  useEffect(() => { onCancelRef.current = onCancel; }, [onCancel]);

  useEffect(() => {
    const previous = document.activeElement;
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancelRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);

  return (
    <div className="close-confirm" role="presentation">
      <section aria-labelledby="deep-link-confirm-title" aria-modal="true" className="close-confirm__panel" role="dialog">
        <h2 id="deep-link-confirm-title">Bu klasörde yeni sohbet açılsın mı?</h2>
        <p>
          Bir bağlantı (<code>fusion://yeni</code>) şu klasörü kök alan yeni bir kod sohbeti istiyor:
        </p>
        <p><code>{kok}</code></p>
        <p>Ajan bu klasördeki dosyaları okuyup değiştirebilir. Bağlantıyı tanımıyorsan vazgeç.</p>
        <div className="close-confirm__actions">
          <button className="close-confirm__cancel" onClick={onCancel} ref={cancelRef} type="button">
            Vazgeç
          </button>
          <button className="close-confirm__confirm" onClick={onConfirm} type="button">
            Sohbeti aç
          </button>
        </div>
      </section>
    </div>
  );
}
