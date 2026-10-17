import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";

/**
 * Zeka — Fusion'ın koddaki zekâ özelliklerini uygulamadan aç/kapat.
 *
 * Bu anahtarlar daha önce yalnız yapılandırma dosyasında ya da terminal komutlarındaydı.
 * Her biri ne yaptığını ve ne kadar maliyet getirdiğini söyler; değişiklik kalıcıdır ve
 * çalışan oturuma hemen uygulanır.
 */

interface Choice { deger: string; etiket: string }
interface Flag { anahtar: string; etiket: string; aciklama: string; maliyet: string; grup: string; acik: boolean }
interface Status {
  motor: string;
  motorlar: Choice[];
  planKipi: string;
  planKipleri: Choice[];
  ogretmenTanimli: boolean;
  bayraklar: Flag[];
}

export function Intelligence({ client }: { client: ProtocolClient }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await client.request("zeka.durum", {});
    if (result.ok !== true) throw new Error(String(result.metin ?? "Zeka ayarları alınamadı."));
    setStatus(result as unknown as Status);
  }, [client]);

  useEffect(() => {
    void load().catch((reason) => setError(errorMessage(reason)));
  }, [load]);

  const change = async (anahtar: string, deger: string | boolean) => {
    setBusy(anahtar);
    setError(null);
    try {
      const result = await client.request("zeka.ayarla", { anahtar, deger });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Ayar kaydedilemedi."));
      setStatus(result as unknown as Status);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  if (!status) {
    return (
      <article className="settings__card" id="settings-intelligence">
        <h3>Zeka</h3>
        {error ? <p className="settings__error" role="alert">{error}</p> : <p className="settings__hint">Okunuyor…</p>}
      </article>
    );
  }

  const groups = [...new Set(status.bayraklar.map((flag) => flag.grup))];
  return (
    <article className="settings__card settings__card--wide" id="settings-intelligence">
      <div className="settings__card-head">
        <div>
          <h3>Zeka</h3>
          <p className="settings__hint">
            Fusion'ın nasıl düşündüğünü, kendini nasıl denetlediğini ve nasıl öğrendiğini buradan yönet.
            Bazıları ek model çağrısı kullanır; maliyet her satırda yazar.
          </p>
        </div>
      </div>

      <fieldset className="settings__fieldset" disabled={busy !== null}>
        <legend>Motor</legend>
        {status.motorlar.map((choice) => (
          <label key={choice.deger} className="settings__choice">
            <input
              checked={status.motor === choice.deger}
              name="zeka-motor"
              onChange={() => void change("motor", choice.deger)}
              type="radio"
            />
            <span>{choice.etiket}</span>
          </label>
        ))}
        <small className="settings__hint">Motor bu oturum için geçerlidir; uygulama yeniden açılınca tek ajana döner.</small>
      </fieldset>

      <fieldset className="settings__fieldset" disabled={busy !== null}>
        <legend>Plan kipi</legend>
        {status.planKipleri.map((choice) => (
          <label key={choice.deger} className="settings__choice">
            <input
              checked={status.planKipi === choice.deger}
              name="zeka-plan"
              onChange={() => void change("planKipi", choice.deger)}
              type="radio"
            />
            <span>{choice.etiket}</span>
          </label>
        ))}
      </fieldset>

      {groups.map((group) => (
        <fieldset key={group} className="settings__fieldset" disabled={busy !== null}>
          <legend>{group}</legend>
          {status.bayraklar
            .filter((flag) => flag.grup === group)
            .map((flag) => (
              <div key={flag.anahtar} className="settings__switch-row">
                <label>
                  <input
                    checked={flag.acik}
                    onChange={(event) => void change(flag.anahtar, event.target.checked)}
                    type="checkbox"
                  />
                  <strong>{flag.etiket}</strong>
                </label>
                <p className="settings__hint">{flag.aciklama}</p>
                <small className="settings__hint">Maliyet: {flag.maliyet}</small>
                {flag.anahtar === "teacherless" && !status.ogretmenTanimli && (
                  <small className="settings__hint"> Öğretmen modeli tanımlı değil; açık olsa da kullanılamaz.</small>
                )}
              </div>
            ))}
        </fieldset>
      ))}
      {error && <p className="settings__error" role="alert">{error}</p>}
    </article>
  );
}
