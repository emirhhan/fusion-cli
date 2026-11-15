import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";

/**
 * Otomatik bellek (P-036): Fusion'ın bu proje için kendi yazdığı `BELLEK.md`.
 * Kullanıcı Markdown'ı burada düzenler; ilk 200 satır / 25 KB her turun bağlamına girer.
 * Claude Code'daki `/memory` ile aynı iş: aç/kapa, düzenle, içe aktar.
 */

interface AutoMemoryState {
  etkin: boolean;
  metin: string;
  dosya: string;
  satir: number;
  bayt: number;
  kirpildi: boolean;
  konular: string[];
  sinirSatir: number;
}

function decode(payload: Record<string, unknown>): AutoMemoryState {
  if (payload.ok !== true) throw new Error(String(payload.metin ?? "Bellek okunamadı."));
  return {
    etkin: payload.etkin !== false,
    metin: typeof payload.metin === "string" ? payload.metin : "",
    dosya: typeof payload.dosya === "string" ? payload.dosya : "",
    satir: typeof payload.satir === "number" ? payload.satir : 0,
    bayt: typeof payload.bayt === "number" ? payload.bayt : 0,
    kirpildi: payload.kirpildi === true,
    konular: Array.isArray(payload.konular) ? payload.konular.filter((item): item is string => typeof item === "string") : [],
    sinirSatir: typeof payload.sinir_satir === "number" ? payload.sinir_satir : 200,
  };
}

export function AutoMemoryPanel({ client }: { client: ProtocolClient }) {
  const [state, setState] = useState<AutoMemoryState | null>(null);
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((payload: Record<string, unknown>) => {
    const next = decode(payload);
    setState(next);
    setDraft(next.metin);
    setDirty(false);
    setError(null);
  }, []);

  const load = useCallback(async () => {
    try {
      apply(await client.request("otobellek.durum", {}));
    } catch (reason) {
      setError(`Bellek okunamadı: ${errorMessage(reason)}`);
    }
  }, [apply, client]);
  useEffect(() => { void load(); }, [load]);

  const run = async (name: string, data: Record<string, unknown>, done: string) => {
    setBusy(true);
    setNotice(null);
    try {
      apply(await client.request(name, data));
      setNotice(done);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally { setBusy(false); }
  };

  const yuklenen = state ? Math.min(state.satir, state.sinirSatir) : 0;
  return <article id="settings-auto-memory" className="settings__card">
    <h3>Otomatik bellek</h3>
    <p className="settings__hint">Fusion'ın bu proje için kendi yazdığı notlar (BELLEK.md). İlk {state?.sinirSatir ?? 200} satır her görevin bağlamına girer ve seçilen model sağlayıcısına gönderilir. Terminalde <code>/memory</code> ve <code># not</code> aynı dosyaya yazar.</p>
    <label className="settings__row settings__row--check">
      <input aria-label="Otomatik belleği kullan" checked={state?.etkin ?? true} disabled={busy || !state} onChange={(event) => void run("otobellek.etkinlestir", { etkin: event.target.checked }, event.target.checked ? "Otomatik bellek açıldı." : "Otomatik bellek kapatıldı.")} type="checkbox" />
      <span>Otomatik belleği kullan</span>
    </label>
    {error && (
      <p className="settings__inline-error" role="alert">
        <span>{error}</span>
        <button className="settings__error-retry" onClick={() => void load()} type="button">Yeniden dene</button>
      </p>
    )}
    {state?.etkin && (
      <>
        <p className="settings__hint" data-testid="auto-memory-status">
          {state.satir === 0 ? "Bellek henüz boş." : `${state.satir} satır · ${(state.bayt / 1024).toFixed(1)} KB · bu oturumda ilk ${yuklenen} satır yüklendi${state.kirpildi ? " (fazlası kırpıldı)" : ""}`}
          {state.konular.length > 0 && ` · konular: ${state.konular.join(", ")}`}
        </p>
        <textarea
          aria-label="Bellek metni"
          className="settings__textarea"
          disabled={busy}
          onChange={(event) => { setDraft(event.target.value); setDirty(true); }}
          rows={12}
          spellCheck={false}
          value={draft}
        />
        <div className="settings__actions">
          <button disabled={busy || !dirty} onClick={() => void run("otobellek.kaydet", { metin: draft }, "Bellek kaydedildi.")} type="button">Belleği kaydet</button>
          <button disabled={busy} onClick={() => void run("otobellek.ice_aktar", { kaynak: "claude" }, "Claude belleği içe aktarıldı.")} type="button">Claude'dan içe aktar</button>
        </div>
        {state.dosya && <p className="settings__hint"><code>{state.dosya}</code></p>}
      </>
    )}
    {notice && <p aria-live="polite" className="settings__hint">{notice}</p>}
  </article>;
}
