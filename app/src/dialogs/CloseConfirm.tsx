import { useEffect, useRef } from "react";
import "./CloseConfirm.css";

/**
 * Kapatma onayı.
 *
 * Kapatmak çalışan turu ve açık sohbetleri sonlandırır; yanlışlıkla basmak
 * (kırmızı düğme, Cmd+Q, Alt+F4) iş kaybettiriyordu. Bu yüzden kapatma isteği
 * Rust tarafında DURDURULUR ve karar burada sorulur.
 */
export function CloseConfirm({
  onCancel,
  onConfirm,
  running,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  /** Tur çalışıyorsa uyarı sertleşir: yarım kalan iş kaybolur. */
  running?: boolean;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Odak VAZGEÇ'te başlar: yanlışlıkla Enter'a basan kapatmasın.
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="close-confirm" role="presentation">
      <section aria-labelledby="close-confirm-title" aria-modal="true" className="close-confirm__panel" role="dialog">
        <h2 id="close-confirm-title">Fusion'ı kapat?</h2>
        <p>
          {running
            ? "Çalışan bir görev var. Kapatırsan yarım kalır ve sonucu kaybolur."
            : "Açık sohbetlerin kapanacak. Geçmişin saklanır."}
        </p>
        <div className="close-confirm__actions">
          <button className="close-confirm__cancel" onClick={onCancel} ref={cancelRef} type="button">
            Vazgeç
          </button>
          <button className="close-confirm__confirm" onClick={onConfirm} type="button">
            Kapat
          </button>
        </div>
      </section>
    </div>
  );
}
