import { useEffect, useRef, useState } from "react";
import { buildIssueUrl, redact, type ReportInput, type ReportKind } from "./report";
import "./FeedbackDialog.css";

async function openWithSystem(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

async function appVersion(): Promise<string> {
  try {
    const { getVersion } = await import("@tauri-apps/api/app");
    return await getVersion();
  } catch {
    // Tarayıcı önizlemesinde Tauri yok; rapor yine gönderilebilir.
    return "bilinmiyor";
  }
}

function platformLabel(): string {
  const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
  if (/Mac/i.test(ua)) return "macOS";
  if (/Windows/i.test(ua)) return "Windows";
  if (/Linux/i.test(ua)) return "Linux";
  return "bilinmiyor";
}

export interface FeedbackDialogProps {
  /** Hata akışından açıldıysa türü, açıklamayı ve teknik ayrıntıyı taşır. */
  initial?: Partial<ReportInput>;
  onClose: () => void;
  openExternal?: (url: string) => Promise<void>;
  loadVersion?: () => Promise<string>;
}

/**
 * Hata bildir / geri bildirim gönder penceresi.
 *
 * Sunucu yoktur: "GitHub'da aç" önceden doldurulmuş issue sayfasını sistem
 * tarayıcısında açar, kullanıcı metni orada görüp kendisi gönderir.
 */
export function FeedbackDialog({ initial, onClose, openExternal = openWithSystem, loadVersion = appVersion }: FeedbackDialogProps) {
  const [tur, setTur] = useState<ReportKind>(initial?.tur ?? "geri-bildirim");
  const [mesaj, setMesaj] = useState(initial?.mesaj ?? "");
  const [ayrintiEkle, setAyrintiEkle] = useState(Boolean(initial?.ayrinti));
  const [surum, setSurum] = useState("bilinmiyor");
  const [durum, setDurum] = useState<"bos" | "acildi" | "hata">("bos");
  const metinRef = useRef<HTMLTextAreaElement>(null);
  const ayrinti = initial?.ayrinti?.trim() ?? "";

  // Çağıranlar `onClose`'u satır içi verir; etki her çizimde yeniden kurulup
  // odağı metin alanına geri çalmasın diye en güncel geri çağırım ref'te tutulur.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const loadVersionRef = useRef(loadVersion);

  useEffect(() => {
    metinRef.current?.focus();
    let iptal = false;
    void loadVersionRef.current().then((value) => { if (!iptal) setSurum(value); });
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onCloseRef.current(); };
    window.addEventListener("keydown", onKey);
    return () => { iptal = true; window.removeEventListener("keydown", onKey); };
  }, []);

  const girdi: ReportInput = { tur, mesaj, ayrinti: ayrintiEkle && ayrinti ? ayrinti : undefined };
  const bosMu = !mesaj.trim() && !girdi.ayrinti;

  const gonder = async () => {
    try {
      await openExternal(buildIssueUrl(girdi, { surum, platform: platformLabel() }));
      setDurum("acildi");
    } catch {
      setDurum("hata");
    }
  };

  return (
    <div className="feedback-dialog__backdrop" role="presentation">
      <section aria-labelledby="feedback-dialog-title" aria-modal="true" className="feedback-dialog" role="dialog">
        <header>
          <h2 id="feedback-dialog-title">{tur === "hata" ? "Hata bildir" : "Geri bildirim gönder"}</h2>
          <button aria-label="Pencereyi kapat" className="feedback-dialog__close" onClick={onClose} type="button">×</button>
        </header>
        <div aria-label="Bildirim türü" className="feedback-dialog__kinds" role="radiogroup">
          <button aria-checked={tur === "hata"} onClick={() => setTur("hata")} role="radio" type="button">Sorun bildir</button>
          <button aria-checked={tur === "geri-bildirim"} onClick={() => setTur("geri-bildirim")} role="radio" type="button">Öneri veya görüş</button>
        </div>
        <label className="feedback-dialog__field">
          <span>{tur === "hata" ? "Ne oldu? Ne yapıyordun?" : "Mesajın"}</span>
          <textarea
            onChange={(event) => { setMesaj(event.target.value); setDurum("bos"); }}
            placeholder={tur === "hata" ? "Örn. Proje açarken uygulama dondu." : "Fusion'da neyi sevdin, neyi değiştirelim?"}
            ref={metinRef}
            value={mesaj}
          />
        </label>
        {ayrinti && (
          <div className="feedback-dialog__details">
            <label className="feedback-dialog__check">
              <input checked={ayrintiEkle} onChange={(event) => setAyrintiEkle(event.target.checked)} type="checkbox" />
              <span>Teknik ayrıntıyı ekle</span>
            </label>
            <details>
              <summary>Gönderilecek ayrıntıyı gör</summary>
              <pre>{redact(ayrinti)}</pre>
            </details>
          </div>
        )}
        <p className="feedback-dialog__note">
          GitHub'da doldurulmuş bir sayfa açılır; göndermeden önce metni orada görürsün. Kullanıcı adın, e-postan ve API anahtarların otomatik gizlenir. Göndermek için GitHub hesabı gerekir.
        </p>
        {durum === "acildi" && <p className="feedback-dialog__status" role="status">GitHub sayfası tarayıcıda açıldı. Orada “Submit new issue” ile gönderebilirsin.</p>}
        {durum === "hata" && <p className="feedback-dialog__status feedback-dialog__status--error" role="alert">Tarayıcı açılamadı. Bağlantını kontrol edip yeniden dene.</p>}
        <footer>
          <button className="feedback-dialog__secondary" onClick={onClose} type="button">{durum === "acildi" ? "Kapat" : "Vazgeç"}</button>
          <button className="feedback-dialog__primary" disabled={bosMu} onClick={() => void gonder()} type="button">GitHub'da aç</button>
        </footer>
      </section>
    </div>
  );
}
