import { useEffect, useRef, useState } from "react";
import type { Mesaj } from "../screens/Conversation";
import "./ShareDialog.css";

/** Dışarı aktarılan metin yalnız kullanıcı ve nihai yanıtları içerir. */
export function shareableTranscript(title: string, messages: Mesaj[]): string {
  const lines = messages.flatMap((message) => {
    if (message.rol !== "kullanici" && message.rol !== "asistan") return [];
    if (message.akan || !message.metin.trim()) return [];
    return [`## ${message.rol === "kullanici" ? "Siz" : "Fusion"}\n\n${message.metin.trim()}`];
  });
  return [`# ${title.trim() || "Fusion sohbeti"}`, ...lines].join("\n\n");
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

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
