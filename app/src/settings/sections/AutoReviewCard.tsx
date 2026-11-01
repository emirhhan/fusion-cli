import { useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { errorMessage } from "../../protocol/result";
import { useAutoReviewStatus, type AutoReviewStatus } from "../../permissions/AutoReviewIndicator";
import { Button } from "../../ui/Button";
import "../../permissions/permissions.css";

type ClassifierSetting = NonNullable<AutoReviewStatus["ayar"]>;

/** `runtime.auto_classifier` seçenekleri; değerler çekirdekteki `AutoClassifierMode` ile aynı. */
export const CLASSIFIER_SETTINGS: readonly { id: ClassifierSetting; etiket: string; aciklama: string }[] = [
  { id: "off", etiket: "Kapalı", aciklama: "Yalnız kurallar; riskli işlem her zaman sorulur." },
  { id: "ask_only", etiket: "Sorulacakları denetle", aciklama: "Kuralın soracağı işlemi model değerlendirir; güvenliyse sorulmaz." },
  { id: "on", etiket: "Tümünü denetle", aciklama: "Ek olarak yazan her kabuk komutu değerlendirilir; riskliyse sorulur. Daha yavaş." },
];

/** Son kararlar listesinde gösterilen satır sayısı. */
const SON_KARAR_SINIRI = 5;

/**
 * Ayarlar › İzinler › Otomatik kip denetçisi (P-011; Claude Code auto mode sınıflandırıcısı).
 *
 * Ayar, model, engel sayacı, Manuel'e düşüş ve son kararlar tek kartta. Yıkıcı işlemler,
 * sudo/sistem ayarı ve `| sh` hiçbir ayarda modele bırakılmaz; bunu kart da söyler.
 */
export function AutoReviewCard({
  client,
  onResumed,
  onSuggestRule,
}: {
  client: Pick<ProtocolClient, "request" | "onEvent">;
  onResumed?: () => void;
  /** Claude Auto mode sekmesi (#83): riskli kararın kalıp önerisini kural formuna al. */
  onSuggestRule?: (kalip: string) => void;
}) {
  const { status, resume, setStatus } = useAutoReviewStatus(client);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!status) return null;

  const choose = async (deger: ClassifierSetting) => {
    if (busy || deger === status.ayar) return;
    setBusy(true); setError(null);
    try {
      const result = (await client.request("oto.ayar", { deger })) as AutoReviewStatus;
      if (result?.ok === false) setError(result.metin || "Denetçi ayarı değiştirilemedi.");
      else setStatus(result);
    } catch (reason) {
      setError(`Denetçi ayarı değiştirilemedi: ${errorMessage(reason)}`);
    } finally {
      setBusy(false);
    }
  };

  const back = async () => {
    setBusy(true);
    const result = await resume();
    setBusy(false);
    if (result?.mod === "auto") onResumed?.();
  };

  const kararlar = (status.son_kararlar ?? []).slice(0, SON_KARAR_SINIRI);
  return (
    <article className="settings__card settings__card--wide" id="settings-auto-review">
      <h3>Otomatik kip denetçisi</h3>
      <p className="settings__hint">
        Otomatik kipte sorulacak bir işlemi küçük bir model kullanıcının mesajlarıyla birlikte değerlendirir.
        Silme gibi geri alınamaz işlemler, sudo, sistem ayarı ve <code>| sh</code> her zaman sorulur.
        Üst üste {status.esik_ardisik ?? 3} ya da toplam {status.esik_toplam ?? 20} riskli kararda oturum Manuel kipe düşer.
      </p>
      <div className="settings__choices" role="group" aria-label="Denetçi ayarı">
        {CLASSIFIER_SETTINGS.map((secenek) => (
          <button
            aria-pressed={secenek.id === status.ayar}
            className="settings__choice"
            data-active={secenek.id === status.ayar}
            disabled={busy}
            key={secenek.id}
            onClick={() => void choose(secenek.id)}
            type="button"
          >
            <strong>{secenek.etiket}</strong>
            <small>{secenek.aciklama}</small>
          </button>
        ))}
      </div>
      <p className="settings__hint">
        Model: {status.model ?? "hakem"}
        {status.model_erisilemiyor ? " — erişilemiyor, kurallar geçerli" : ""} · Engel: {status.ardisik ?? 0}/{status.esik_ardisik ?? 3} üst üste,{" "}
        {status.toplam ?? 0}/{status.esik_toplam ?? 20} toplam
      </p>
      {status.veri_notu && <p className="settings__hint">{status.veri_notu}</p>}
      {status.dustu && status.mod === "security" && (
        <div className="settings__warning" role="alert">
          <p>Oturum Manuel kipe düştü: {status.dusus_nedeni}.</p>
          <div className="settings__actions">
            <Button disabled={busy} onClick={() => void back()} variant="secondary">Otomatik'e dön</Button>
          </div>
        </div>
      )}
      {error && <p className="settings__hint" role="alert">{error}</p>}
      {kararlar.length > 0 && (
        <ul aria-label="Son denetçi kararları" className="auto-review-card__list">
          {kararlar.map((karar, sira) => (
            <li data-verdict={karar.karar} key={`${sira}:${karar.arac}:${karar.ozet}`}>
              <strong>{karar.karar_etiketi}</strong> [{karar.kaynak}] {karar.ozet} — {karar.gerekce}
              {onSuggestRule && karar.karar === "riskli" && (karar.oneri ? (
                <Button
                  aria-label={`${karar.oneri} kuralını forma al`}
                  onClick={() => onSuggestRule(karar.oneri ?? "")}
                  variant="secondary"
                >
                  İzin kuralı öner
                </Button>
              ) : (
                <small> · öneri yok (joker ya da kısaltılmış özet); kalıbı kurallara sen yaz</small>
              ))}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
