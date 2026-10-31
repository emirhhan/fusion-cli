import { setNotificationPreference, type BildirimTercihleri } from "../../notifications/preferences";
import { playChime } from "../../notifications/sound";
import { useNotificationPreferences } from "../../notifications/useTurnNotifications";

/**
 * Bildirimler — hangi olay işletim sistemi bildirimi üretir (P-047).
 *
 * Her olay ayrı anahtardır; Claude Code masaüstü "tur bitti" ve "izin bekliyor"
 * için bildirir, Fusion buna arka plandaki (zamanlanmış ya da başka) sohbeti ekler.
 * Ses isteğe bağlıdır ve varsayılan kapalıdır.
 */

const SATIRLAR: { anahtar: keyof BildirimTercihleri; id: string; etiket: string; ipucu: string }[] = [
  { anahtar: "turBitti", id: "settings-notify-turn", etiket: "Bakılan sohbetin turu bitince", ipucu: "Yalnız Fusion penceresi odakta değilken gönderilir." },
  { anahtar: "onayBekliyor", id: "settings-notify-approval", etiket: "Onay ya da cevap beklerken", ipucu: "Onay kartı görünmüyorsa (başka sohbet ya da başka uygulama) haber verir." },
  { anahtar: "arkaPlanBitti", id: "settings-notify-background", etiket: "Arka plandaki sohbet bitince", ipucu: "Zamanlanmış görevler ve seçili olmayan sohbetler için." },
];

export function Notifications() {
  const tercihler = useNotificationPreferences();
  return (
    <>
      <article className="settings__card" id="settings-notifications">
        <h3>İşletim sistemi bildirimleri</h3>
        <p className="settings__hint">
          Bildirimler bir sohbete bakmadığın anlarda gelir; kenar çubuğunda o sohbet okunmamış işaretlenir ve Dock
          simgesinde sayı görünür. Sohbeti açınca işaret kalkar.
        </p>
        {SATIRLAR.map((satir) => (
          // Açıklama kendi satırına aittir: çizgi açıklamanın ALTINDA durur. Eskiden çizgi etiketle
          // açıklamanın arasına giriyor, açıklama bir sonraki ayarın başlığı gibi okunuyordu.
          <div className="settings__row-group" key={satir.anahtar}>
            <label className="settings__row settings__row--check">
              <input
                aria-describedby={`${satir.id}-ipucu`}
                checked={tercihler[satir.anahtar]}
                id={satir.id}
                onChange={(event) => setNotificationPreference(satir.anahtar, event.target.checked)}
                type="checkbox"
              />
              <span>{satir.etiket}</span>
            </label>
            <p className="settings__hint" id={`${satir.id}-ipucu`}>{satir.ipucu}</p>
          </div>
        ))}
      </article>
      <article className="settings__card">
        <h3>Ses</h3>
        <label className="settings__row settings__row--check">
          <input
            checked={tercihler.ses}
            id="settings-notify-sound"
            onChange={(event) => setNotificationPreference("ses", event.target.checked)}
            type="checkbox"
          />
          <span>Bildirimle birlikte kısa bir ses çal</span>
        </label>
        <div className="settings__actions">
          <button onClick={() => playChime()} type="button">Sesi dene</button>
        </div>
      </article>
    </>
  );
}
