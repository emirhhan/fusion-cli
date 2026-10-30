import { useEffect, useRef, useState } from "react";
import type { Mesaj } from "../screens/Conversation";
import "./ShareDialog.css";

/**
 * Mesaj metnindeki satır başı başlık işaretleri kaçırılır: gövdede yazılan `## Siz` satırı
 * rol başlığını taklit edip aktarımı sahteleyemesin (U4-21).
 */
function escapeHeadings(text: string): string {
  return text.replace(/^(\s{0,3})(#{1,6})(?=\s)/gm, "$1\\$2");
}

/**
 * Dışarı aktarılan metin yalnız kullanıcı ve nihai yanıtları içerir. Hata mesajları (iç yol ve
 * ayrıntı taşıyabilir) ve ara anlatımlar dahil edilmez; başlık tek satıra indirilir.
 */
export function shareableTranscript(title: string, messages: Mesaj[]): string {
  const lines = messages.flatMap((message) => {
    if (message.rol !== "kullanici" && message.rol !== "asistan") return [];
    if (message.akan || message.hata || message.ara || !message.metin.trim()) return [];
    return [`## ${message.rol === "kullanici" ? "Siz" : "Fusion"}\n\n${escapeHeadings(message.metin.trim())}`];
  });
  const baslik = title.replace(/\s+/g, " ").trim();
  return [`# ${baslik || "Fusion sohbeti"}`, ...lines].join("\n\n");
}

export function ShareDialog({ title, messages, onClose }: {
  title: string;
  messages: Mesaj[];
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const transcript = shareableTranscript(title, messages);

  // Sohbet değiştiyse "Kopyalandı" bayatlar (U4-21).
  useEffect(() => { setCopied(false); }, [transcript]);

  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [onClose]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(transcript);
      setCopied(true);
      setError(null);
    } catch {
      setError("Panoya kopyalanamadı. Metni seçip elle kopyalayabilirsin.");
    }
  };

  return (
    <div className="share-dialog__backdrop" role="presentation">
      <section aria-labelledby="share-dialog-title" aria-modal="true" className="share-dialog" role="dialog">
        <header>
          <h2 id="share-dialog-title">Sohbeti paylaş</h2>
          <button aria-label="Paylaşımı kapat" onClick={onClose} ref={closeRef} type="button">×</button>
        </header>
        <p>Yalnız mesaj metinleri kopyalanır; ek dosyalar ve işlem kayıtları eklenmez. Mesajların içinde yazan dosya yollarını paylaşmadan önce kontrol et.</p>
        <textarea aria-label="Paylaşılacak sohbet metni" readOnly value={transcript} />
        {error && <p role="alert">{error}</p>}
        <footer><button onClick={() => void copy()} type="button">{copied ? "Kopyalandı" : "Metni kopyala"}</button></footer>
      </section>
    </div>
  );
}
