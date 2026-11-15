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

/** Çekirdekten tam dışa aktarım (`sohbet.disa_aktar`): araç çağrıları katlanmış, sırlar maskeli (P-028). */
export type ExportFormat = "markdown" | "json";
export type ExportFetcher = (format: ExportFormat) => Promise<{ metin: string; dosya_adi?: string }>;

export function downloadText(text: string, fileName: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function ShareDialog({ title, messages, onClose, onExport }: {
  title: string;
  messages: Mesaj[];
  onClose: () => void;
  /** Verilirse biçim seçici ve "Dosyaya kaydet" görünür; metin çekirdekten gelir. */
  onExport?: ExportFetcher;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [format, setFormat] = useState<ExportFormat>("markdown");
  const [exported, setExported] = useState<{ metin: string; dosya_adi?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  // Satır içi onClose her render'da efekti yeniden kurup odağı kapat düğmesine çekiyordu (U4-51).
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  const fallback = shareableTranscript(title, messages);
  const transcript = exported?.metin ?? fallback;

  // Sohbet ya da biçim değiştiyse "Kopyalandı" bayatlar (U4-21).
  useEffect(() => { setCopied(false); }, [transcript]);

  // Çekirdek dışa aktarımı: biçim ya da TAMAMLANMIŞ mesaj sayısı değişince yeniden alınır; hata
  // olursa yerel metne düşülür. Ölçüldü (31 Ekim): `messages` referansına bağlıyken akış sürerken
  // her tokende tam geçmiş sunucuda yeniden maskeleniyordu.
  const settledCount = messages.filter((message) => !message.akan).length;
  useEffect(() => {
    if (!onExport) return;
    let alive = true;
    setLoading(true);
    onExport(format)
      .then((result) => { if (alive) { setExported(result); setError(null); } })
      .catch(() => { if (alive) { setExported(null); setError("Tam dışa aktarım alınamadı; yalnız mesaj metinleri gösteriliyor."); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [onExport, format, settledCount]);

  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onCloseRef.current(); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(transcript);
      setCopied(true);
      setError(null);
    } catch {
      setError("Panoya kopyalanamadı. Metni seçip elle kopyalayabilirsin.");
    }
  };

  // Yalnız çekirdekten gelen metin kaydedilir: yedek Markdown `application/json` adıyla inmesin.
  const save = () => {
    if (!exported || loading) return;
    const name = exported.dosya_adi ?? `fusion-sohbet.${format === "json" ? "json" : "md"}`;
    try {
      downloadText(exported.metin, name, format === "json" ? "application/json" : "text/markdown");
    } catch {
      setError("Dosya kaydedilemedi. Metni kopyalayıp elle kaydedebilirsin.");
    }
  };

  return (
    <div className="share-dialog__backdrop" role="presentation">
      <section aria-labelledby="share-dialog-title" aria-modal="true" className="share-dialog" role="dialog">
        <header>
          <h2 id="share-dialog-title">Sohbeti paylaş</h2>
          <button aria-label="Paylaşımı kapat" onClick={onClose} ref={closeRef} type="button">×</button>
        </header>
        <p>Yalnız mesaj metinleri kopyalanır; ek dosyalar eklenmez, araç çağrıları katlanmış ve kırpılmış gelir, sırlar maskelenir. Mesajların içinde yazan dosya yollarını paylaşmadan önce kontrol et.</p>
        {onExport && (
          <div className="share-dialog__formats" role="radiogroup" aria-label="Dışa aktarım biçimi">
            {(["markdown", "json"] as const).map((item) => (
              <label key={item}>
                <input checked={format === item} name="share-format" onChange={() => setFormat(item)} type="radio" value={item} />
                {item === "markdown" ? "Markdown" : "JSON"}
              </label>
            ))}
          </div>
        )}
        <textarea aria-label="Paylaşılacak sohbet metni" readOnly value={transcript} />
        {error && <p role="alert">{error}</p>}
        <footer>
          {onExport && (
            <button className="share-dialog__secondary" disabled={loading || !exported} onClick={save} type="button">
              Dosyaya kaydet
            </button>
          )}
          <button onClick={() => void copy()} type="button">{copied ? "Kopyalandı" : "Metni kopyala"}</button>
        </footer>
      </section>
    </div>
  );
}
