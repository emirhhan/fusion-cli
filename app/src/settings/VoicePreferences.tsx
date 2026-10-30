import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import { VoiceSettings, type VoicePrefs } from "../voice/VoiceSettings";
import "../voice/VoiceMode.css";

interface VoiceStatus {
  ayar: VoicePrefs;
  kullanilabilir: boolean;
  model_kurulu: boolean;
  motor: string;
  ses: string | null;
  turkce: boolean;
  yukseltme: string | null;
}

const DEFAULT_PREFS: VoicePrefs = { hiz: 1 };

/** Ayarlar ekranındaki kalıcı ses tercihi (hız) ve ses motoru durumu. */
export function VoicePreferences({ client }: { client: ProtocolClient }) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [prefs, setPrefs] = useState<VoicePrefs>(DEFAULT_PREFS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = (await client.request("ses.durum", {})) as unknown as VoiceStatus & {
      metin?: string;
      ok?: boolean;
    };
    if (!result.ok || !result.ayar) {
      throw new Error(result.metin ?? "Ses ayarları alınamadı.");
    }
    setStatus(result);
    setPrefs(result.ayar);
  }, [client]);

  // Gerçek neden gösterilir ve yeniden dene sunulur (U2-47); eskiden sabit metin gerçek nedeni atıyordu.
  const retry = useCallback(() => {
    setError(null);
    void load().catch((reason) => setError(`Ses ayarları alınamadı: ${errorMessage(reason)}`));
  }, [load]);
  useEffect(() => { retry(); }, [retry]);

  /** Kayıt sürerken gelen son değer sıraya alınır; sürgü devre dışı kalmaz (odak kaybolmasın, U2-45). */
  const kayitta = useRef(false);
  const bekleyen = useRef<VoicePrefs | null>(null);
  const save = async (next: VoicePrefs): Promise<void> => {
    if (kayitta.current) { bekleyen.current = next; return; }
    kayitta.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await client.request("ses.ayar", { ...next });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Ses ayarı kaydedilemedi."));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ses ayarı kaydedilemedi.");
    } finally {
      kayitta.current = false;
      setBusy(false);
      const sonraki = bekleyen.current;
      bekleyen.current = null;
      if (sonraki && sonraki.hiz !== next.hiz) void save(sonraki);
    }
  };

  return (
    <article className="settings__card settings__card--wide">
      <div className="settings__card-head">
        <div>
          <h3>Ses</h3>
          <p className="settings__hint">Konuşma hızı ve çevrimdışı Türkçe ses (EMA Lightning).</p>
        </div>
        <span className="settings__badge">
          {status ? `${status.motor === "ema" ? "EMA Lightning" : "Sistem"} · ${status.ses ?? "ses yok"}` : "Okunuyor…"}
        </span>
      </div>

      {status ? (
        <VoiceSettings
          busy={busy}
          onChange={(next) => void save(next)}
          onTop={false}
          onTopChange={() => undefined}
          prefs={prefs}
          showOnTop={false}
        />
      ) : (
        <p aria-live="polite" className="settings__hint">Ses ayarları okunuyor…</p>
      )}

      {status?.yukseltme && <p className="settings__hint">{status.yukseltme}</p>}
      {error && (
        <p className="settings__error" role="alert">
          {error}{" "}
          {!status && <button className="settings__error-retry" onClick={retry} type="button">Yeniden dene</button>}
        </p>
      )}
    </article>
  );
}
