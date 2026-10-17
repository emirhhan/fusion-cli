import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import { ChoiceCards, PanelGroup, PanelIntro, ToggleRow } from "./PanelParts";

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
        <h3 className="settings__section-heading">Zeka</h3>
        {error ? <p className="px-error" role="alert">{error}</p> : <p className="px-empty">Okunuyor…</p>}
      </article>
    );
  }

  const groups = [...new Set(status.bayraklar.map((flag) => flag.grup))];
  const busyAny = busy !== null;
  return (
    <article className="settings__card" id="settings-intelligence">
      <PanelIntro title="Zeka">
        Fusion'ın nasıl düşündüğünü, kendini nasıl denetlediğini ve nasıl öğrendiğini buradan yönet.
        Bazıları ek model çağrısı kullanır; maliyet her satırda yazar.
      </PanelIntro>

      <ChoiceCards
        disabled={busyAny}
        legend="Motor"
        name="zeka-motor"
        note="Motor bu oturum için geçerlidir; uygulama yeniden açılınca tek ajana döner."
        onChange={(value) => void change("motor", value)}
        options={status.motorlar.map((choice) => ({ value: choice.deger, title: choice.etiket }))}
        value={status.motor}
      />

      <ChoiceCards
        disabled={busyAny}
        legend="Plan kipi"
        name="zeka-plan"
        onChange={(value) => void change("planKipi", value)}
        options={status.planKipleri.map((choice) => ({ value: choice.deger, title: choice.etiket }))}
        value={status.planKipi}
      />

      {groups.map((group) => (
        <PanelGroup key={group} title={group}>
          {status.bayraklar
            .filter((flag) => flag.grup === group)
            .map((flag) => (
              <ToggleRow
                checked={flag.acik}
                chip={`Maliyet: ${flag.maliyet}`}
                description={flag.aciklama}
                disabled={busyAny}
                key={flag.anahtar}
                onChange={(checked) => void change(flag.anahtar, checked)}
                title={flag.etiket}
                warning={
                  flag.anahtar === "teacherless" && !status.ogretmenTanimli
                    ? "Öğretmen modeli tanımlı değil; açık olsa da kullanılamaz."
                    : undefined
                }
              />
            ))}
        </PanelGroup>
      ))}
      {error && <p className="px-error" role="alert">{error}</p>}
    </article>
  );
}
