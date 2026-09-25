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
}

export function ChromeBrowser({ client }: { client: ProtocolClient }) {
  const [state, setState] = useState<ChromeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [extensionPath, setExtensionPath] = useState("");

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

  return (
    <article className="settings__card">
      <h3>Chrome eklentisi</h3>
      <p className="settings__hint">Fusion Browser eklentisiyle açık Chrome sekmenizi seçip site izni verebilirsiniz. İzinli sekme Fusion araçlarına ve yan panel sohbetine açılır.</p>
      <p className="settings__hint">Durum: {state?.bagli ? "Eklenti bağlı" : state?.calisiyor ? "Eklenti bekleniyor" : "Kapalı"}</p>
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
      <p className="settings__hint">Chrome → Uzantılar → Geliştirici modu → Paketlenmemiş öğe yükle yolundan Fusion Browser klasörünü seçin; ardından uzantı simgesini açıp port ve anahtarı girin.</p>
      {extensionPath && <p className="settings__hint">Paketli eklenti klasörü: <code>{extensionPath}</code></p>}
      {error && <p className="settings__inline-error" role="alert">{error}</p>}
    </article>
  );
}
