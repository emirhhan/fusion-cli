import { useCallback, useEffect, useState } from "react";
import { selectVoiceModel } from "../platform/dialog";
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

const DEFAULT_PREFS: VoicePrefs = { hiz: 1, model: null, robotik: 0.5 };

/** Ayarlar ekranındaki kalıcı ses tercihleri ve çevrimdışı model kurulumu. */
export function VoicePreferences({
  client,
  selectModel = selectVoiceModel,
}: {
  client: ProtocolClient;
  selectModel?: () => Promise<string | null>;
}) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [prefs, setPrefs] = useState<VoicePrefs>(DEFAULT_PREFS);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
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

  useEffect(() => {
    if (typeof client.onEvent !== "function") return;
    return client.onEvent((event) => {
      if (event.olay !== "SesModeliIlerleme") return;
      const downloaded = Number(event.inen ?? 0);
      const total = Number(event.toplam ?? 0);
      if (downloaded > 0 && total > 0) {
        setProgress(Math.min(100, Math.round((downloaded / total) * 100)));
      }
    });
  }, [client]);

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

  const pickModel = async () => {
    try {
      const model = await selectModel();
      if (model) await save({ ...prefs, model });
    } catch {
      setError("Ses modeli seçilemedi.");
    }
  };

  const download = async () => {
    setBusy(true);
    setProgress(0);
    setError(null);
    try {
      const result = await client.request("ses.model_indir", {});
      if (result.ok !== true) throw new Error(String(result.metin ?? "Ses modeli indirilemedi."));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ses modeli indirilemedi.");
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  return (
    <article className="settings__card settings__card--wide">
      <div className="settings__card-head">
        <div>
          <h3>Ses</h3>
          <p className="settings__hint">Konuşma hızı, tını ve çevrimdışı Türkçe model.</p>
        </div>
        <span className="settings__badge">
          {status ? `${status.motor === "piper" ? "Piper" : "Sistem"} · ${status.ses ?? "ses yok"}` : "Okunuyor…"}
        </span>
      </div>

      {status ? (
        <VoiceSettings
          disabled={busy}
          onChange={(next) => void save(next)}
          onPickModel={() => void pickModel()}
          onTop={false}
          onTopChange={() => undefined}
          prefs={prefs}
          showOnTop={false}
        />
      ) : (
        <p aria-live="polite" className="settings__hint">Ses ayarları okunuyor…</p>
      )}

      {!status?.model_kurulu && (
        <div className="settings__actions">
          <button disabled={busy} onClick={() => void download()} type="button">
            {progress === null ? "Türkçe modeli indir" : `İndiriliyor · %${progress}`}
          </button>
          <small>Yaklaşık 60 MB · çevrimdışı · MIT lisanslı</small>
        </div>
      )}
      {status?.yukseltme && <p className="settings__hint">{status.yukseltme}</p>}
      {error && <p className="settings__error" role="alert">{error}</p>}
    </article>
  );
}
