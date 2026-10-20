import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
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

  useEffect(() => {
    void load().catch(() => setError("Ses ayarları alınamadı."));
  }, [load]);

  const save = async (next: VoicePrefs) => {
    setBusy(true);
    setError(null);
    try {
      const result = await client.request("ses.ayar", { ...next });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Ses ayarı kaydedilemedi."));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ses ayarı kaydedilemedi.");
    } finally {
      setBusy(false);
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
          disabled={busy}
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
      {error && <p className="settings__error" role="alert">{error}</p>}
    </article>
  );
}
