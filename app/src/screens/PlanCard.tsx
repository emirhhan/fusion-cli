import "./PlanCard.css";

/** Plan dosyasını sistemin varsayılan editöründe aç; opener yoksa sessizce vazgeç. */
async function openPlanFile(path: string): Promise<boolean> {
  try {
    const { openPath } = await import("@tauri-apps/plugin-opener");
    await openPath(path);
    return true;
  } catch {
    return false;
  }
}

/** Plan dosyasının bulunduğu klasörü Finder/Explorer'da göster. */
async function revealPlanFile(path: string): Promise<boolean> {
  try {
    const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
    await revealItemInDir(path);
    return true;
  } catch {
    return false;
  }
}

/**
 * Plan kipinde biten turun plan dosyası kartı (P-025).
 *
 * Çekirdek planı `plans/<sohbet>.md` dosyasına yazar ve `PlanDrafted` yayınlar;
 * kart yolu gösterir ve Claude Code'un Ctrl+G'si gibi dosyayı editörde açar.
 * Planın metni ayrıca gösterilmez: asistan cevabı olarak hemen üstte durur.
 */
export function PlanCard({
  baslik,
  yol,
  onOpen = openPlanFile,
  onReveal = revealPlanFile,
}: {
  baslik: string;
  yol: string;
  onOpen?: (path: string) => Promise<boolean>;
  onReveal?: (path: string) => Promise<boolean>;
}) {
  return (
    <section aria-label="Plan dosyası kaydedildi" className="plan-card">
      <span aria-hidden="true" className="plan-card__dot" />
      <div className="plan-card__body">
        <strong className="plan-card__title">{baslik}</strong>
        <span className="plan-card__meta">
          Plan dosyası · <code>{yol}</code>
        </span>
      </div>
      <div className="plan-card__actions">
        <button className="plan-card__button plan-card__button--primary" onClick={() => void onOpen(yol)} type="button">
          Editörde aç
        </button>
        <button className="plan-card__button" onClick={() => void onReveal(yol)} type="button">
          Konumunu göster
        </button>
      </div>
    </section>
  );
}
