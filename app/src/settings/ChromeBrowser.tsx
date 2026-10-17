import { useEffect, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import type { ProtocolClient } from "../protocol/client";

interface ChromeStatus {
  ok: boolean;
  calisiyor: boolean;
  bagli: boolean;
  port: number | null;
  anahtar: string | null;
  metin?: string;
  eklenti_yuklu?: boolean;
  eklenti_etkin?: boolean;
  eklenti_surum?: string | null;
  yol?: string;
  adimlar?: string[];
  asama?: "yuklendi" | "izin_gerekli" | "elle" | "desteklenmiyor" | "hata";
}

type Check = "ok" | "wait" | "off";

/** Kurulumun iki doğrulaması: Chrome'da yüklü/etkin mi, Fusion'la el sıkıştı mı. */
export function installChecks(state: ChromeStatus | null): { loaded: Check; paired: Check } {
  const loaded: Check = state?.eklenti_yuklu ? (state.eklenti_etkin ? "ok" : "wait") : "off";
  const paired: Check = state?.bagli ? "ok" : state?.calisiyor ? "wait" : "off";
  return { loaded, paired };
}

const CHECK_TEXT: Record<Check, string> = { ok: "Tamam", wait: "Bekleniyor", off: "Yok" };

export function ChromeBrowser({ client }: { client: ProtocolClient }) {
  const [state, setState] = useState<ChromeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [extensionPath, setExtensionPath] = useState("");
  const [steps, setSteps] = useState<string[]>([]);

  useEffect(() => {
    if (!isTauri()) return;
    let mounted = true;
    void import("@tauri-apps/api/path").then(async ({ join, resourceDir }) => {
      const path = await join(await resourceDir(), "chrome-extension");
      if (mounted) setExtensionPath(path);
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => client.request("chrome.durum", {}).then((value) => {
      if (mounted) setState((previous) => {
        const next = value as unknown as ChromeStatus;
        return next.calisiyor && previous?.port === next.port
          ? { ...next, anahtar: previous.anahtar ?? next.anahtar }
          : next;
      });
    }).catch(() => { if (mounted) setError("Chrome durumu okunamadı."); });
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 4000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, [client]);

  const update = async (name: "chrome.baslat" | "chrome.durdur") => {
    setBusy(true);
    setError("");
    try {
      const result = await client.request(name, {}) as unknown as ChromeStatus;
      if (!result.ok) throw new Error(result.metin || "Bağlantı değiştirilemedi.");
      setState(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Chrome bağlantısı değiştirilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const install = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await client.request("chrome.kur", {}) as unknown as ChromeStatus;
      if (!result.ok) throw new Error(result.metin || "Kurulum başlatılamadı.");
      setState(result);
      setSteps(result.asama === "yuklendi" ? [] : result.adimlar ?? []);
      if (result.asama === "izin_gerekli" || result.asama === "elle") setError(result.metin ?? "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Kurulum başlatılamadı.");
    } finally {
      setBusy(false);
    }
  };

  const checks = installChecks(state);
  const complete = checks.loaded === "ok" && checks.paired === "ok";

  return (
    <article className="settings__card">
      <h3>Chrome eklentisi</h3>
      <p className="settings__hint">Fusion Browser eklentisiyle açık Chrome sekmenizi seçip site izni verebilirsiniz. İzinli sekme Fusion araçlarına ve yan panel sohbetine açılır.</p>
      <ul className="settings__checks" aria-label="Kurulum durumu">
        <li data-state={checks.loaded}><span>Chrome'a yüklendi</span><b>{CHECK_TEXT[checks.loaded]}</b></li>
        <li data-state={checks.paired}><span>Fusion ile eşleşti</span><b>{CHECK_TEXT[checks.paired]}</b></li>
      </ul>
      {!complete && (
        <div className="settings__actions">
          <button disabled={busy} onClick={() => void install()} type="button">Eklentiyi kur</button>
          <small>Chrome tek bir onay ister; gerisini Fusion yapar.</small>
        </div>
      )}
      {steps.length > 0 && !complete && (
        <ol className="settings__steps">{steps.map((step) => <li key={step}>{step}</li>)}</ol>
      )}
      <div className="settings__actions">
        <button disabled={busy} onClick={() => void update(state?.calisiyor ? "chrome.durdur" : "chrome.baslat")} type="button">
          {state?.calisiyor ? "Bağlantıyı kapat" : "Bağlantıyı başlat"}
        </button>
        {state?.calisiyor && !state.anahtar && (
          <button disabled={busy} onClick={() => void update("chrome.baslat")} type="button">Anahtarı göster</button>
        )}
      </div>
      {state?.calisiyor && state.anahtar && (
        <div className="settings__form">
          <label htmlFor="chrome-port">Yerel port</label>
          <input id="chrome-port" readOnly value={state.port ?? ""} />
          <label htmlFor="chrome-key">Eşleştirme anahtarı</label>
          <input id="chrome-key" readOnly value={state.anahtar} />
        </div>
      )}
      <p className="settings__hint">Kurulum bittikten sonra Fusion açıkken eklenti kendiliğinden bağlanır; port ve anahtar yalnız elle bağlanmak için gerekir. Oturumlarınıza ve çerezlerinize dokunulmaz.</p>
      {extensionPath && <p className="settings__hint">Paketli eklenti klasörü: <code>{extensionPath}</code></p>}
      {error && <p className="settings__inline-error" role="alert">{error}</p>}
    </article>
  );
}
