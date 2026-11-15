import { useState } from "react";
import "./PlanCard.css";

/** Düğme başarısız olunca kartta gösterilen metinler; yol kartta zaten yazılıdır. */
export const PLAN_OPEN_FAILED = "Dosya editörde açılamadı; yolu kopyalayıp kendin aç.";
export const PLAN_REVEAL_FAILED = "Konum gösterilemedi; yolu kopyalayıp kendin aç.";

/**
 * Plan dosyasını sistemin varsayılan editöründe aç; izin ya da eklenti yoksa false.
 *
 * Ölçüldü (31 Ekim): `opener:default` kümesi open_path içermiyor; yetki dosyasında
 * `opener:allow-open-path` + plan dizini kapsamı olmadan çağrı reddediliyor ve hata
 * yutulduğu için düğme ölü görünüyordu. Kapsam `src-tauri/capabilities/default.json`.
 */
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
  const [hata, setHata] = useState<string | null>(null);
  const attempt = async (action: (path: string) => Promise<boolean>, failure: string) => {
    setHata(null);
    const ok = await action(yol).catch(() => false);
    if (!ok) setHata(failure);
  };
  return (
    <section aria-label="Plan dosyası kaydedildi" className="plan-card">
      <span aria-hidden="true" className="plan-card__dot" />
      <div className="plan-card__body">
        <strong className="plan-card__title">{baslik}</strong>
        <span className="plan-card__meta">
          Plan dosyası · <code>{yol}</code>
        </span>
        {hata && (
          <span className="plan-card__error" role="alert">
            {hata}
          </span>
        )}
      </div>
      <div className="plan-card__actions">
        <button className="plan-card__button plan-card__button--primary" onClick={() => void attempt(onOpen, PLAN_OPEN_FAILED)} type="button">
          Editörde aç
        </button>
        <button className="plan-card__button" onClick={() => void attempt(onReveal, PLAN_REVEAL_FAILED)} type="button">
          Konumunu göster
        </button>
      </div>
    </section>
  );
}
