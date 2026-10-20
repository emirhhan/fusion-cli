import "./PreviewCard.css";

const KIND_LABEL: Record<string, string> = {
  wordpress: "WordPress",
  php: "PHP",
  node: "Node",
  static: "Statik site",
};

async function openInBrowser(url: string): Promise<void> {
  try {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } catch {
    window.open(url, "_blank", "noopener");
  }
}

/**
 * Ajanın çalıştırdığı sitenin kartı: adres, tür ve iki eylem.
 *
 * Ölçüldü (2 Ekim): kullanıcı "nasıl önizlerim" diye sordu, kurulum rehberi aldı.
 * Artık site çalıştırılınca sohbette tek tıkla açılan bir kart durur.
 */
export function PreviewCard({
  url,
  baslik,
  tur,
  onOpen,
}: {
  url: string;
  baslik?: string;
  tur?: string;
  onOpen?: (url: string) => void;
}) {
  const label = tur ? KIND_LABEL[tur] ?? tur : "Site";
  return (
    <section aria-label="Önizleme hazır" className="preview-card">
      <span aria-hidden="true" className="preview-card__dot" />
      <div className="preview-card__body">
        <strong className="preview-card__title">{baslik || "Önizleme hazır"}</strong>
        <span className="preview-card__meta">
          {label} · <code>{url}</code>
        </span>
      </div>
      <div className="preview-card__actions">
        {onOpen && (
          <button className="preview-card__button preview-card__button--primary" onClick={() => onOpen(url)} type="button">
            Uygulamada aç
          </button>
        )}
        <button className="preview-card__button" onClick={() => void openInBrowser(url)} type="button">
          Tarayıcıda aç
        </button>
      </div>
    </section>
  );
}
