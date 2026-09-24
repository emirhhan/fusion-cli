import { Button } from "../../ui/Button";

/**
 * Modeller — hangi modelle çalışıldığı ve nasıl değiştirileceği.
 *
 * Eskiden Kontrol Paneli'nde "Ajan / Hakem / Adaylar / Yönlendirme" diye dört
 * satır vardı ve hepsi aynı anda görünüyordu. Oysa AJAN MODUNDA tek model
 * çalışır; hakem ve aday havuzu yalnız Fusion motorunun çok modelli akışına
 * aittir. İkisini birlikte göstermek, agent turunda hiç kullanılmayan
 * kavramları kullanıcının önüne koyuyordu.
 *
 * "Düşünme düzeyi" (`/level`) buradan kaldırıldı: web sağlayıcı çağında
 * karşılığı yok.
 */

export interface ModelState {
  agent: string;
  hakem: string;
  adaylar: string[];
  saglayici: string;
  ogretmen?: string;
  ogretmen_etiket?: string;
}

export function Models({
  model,
  onRunCommand,
}: {
  model: ModelState | null;
  /** CLI komutunu çalıştırır. Verilmezse değiştirme düğmeleri çizilmez. */
  onRunCommand?: (command: string) => void;
}) {
  if (!model) return <p className="settings__hint">Model bilgisi okunamadı.</p>;
  return (
    <>
      <article className="settings__card">
        <h3>Ajan modeli</h3>
        <p className="settings__stat">{model.agent || "seçilmedi"}</p>
        <p className="settings__hint">
          Ajan modunda çalışan tek model budur. Sohbet ekranında, görev kutusunun
          sağındaki seçiciden de değiştirebilirsin.
        </p>
        <p className="settings__hint">
          Öğretmen: {model.ogretmen_etiket || model.ogretmen || "bağlı değil"}.
          Bağlıysa ajan uzun kod görevinde takıldığında bu web oturumuna bir kez danışır.
        </p>
        {onRunCommand && (
          <div className="settings__actions">
            <Button onClick={() => onRunCommand("/model")} variant="secondary">
              Modeli değiştir
            </Button>
            <Button onClick={() => onRunCommand("/development")} variant="secondary">
              Bağlı sağlayıcıların modellerini getir
            </Button>
          </div>
        )}
      </article>

      <article className="settings__card">
        <h3>Fusion motoru</h3>
        <p className="settings__hint">
          Fusion modu aynı görevi birden çok modele verir, sonuçları bir hakem modelle
          karşılaştırır ve kazananı seçer. Bu alanlar YALNIZ o modda kullanılır; ajan
          modunu etkilemez.
        </p>
        <dl className="settings__pairs">
          <dt>Hakem</dt>
          <dd>{model.hakem || "—"}</dd>
          <dt>Aday havuzu</dt>
          <dd>{model.adaylar.length > 0 ? model.adaylar.join(" · ") : "Yok"}</dd>
          <dt>Sağlayıcı</dt>
          <dd>{model.saglayici || "—"}</dd>
        </dl>
        {onRunCommand && (
          <div className="settings__actions">
            <Button onClick={() => onRunCommand("/mode")} variant="secondary">
              Model profilini değiştir
            </Button>
          </div>
        )}
      </article>
    </>
  );
}
