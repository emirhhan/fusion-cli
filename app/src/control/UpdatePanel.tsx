import { isTauri } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

export function UpdatePanel() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Yeni sürümü kontrol edebilirsin.");
  useEffect(() => () => { void update?.close().catch(() => undefined); }, [update]);
  if (!isTauri()) return null;

  const inspect = async () => {
    setBusy(true);
    setMessage("Güncelleme kontrol ediliyor…");
    try {
      const next = await check({ timeout: 15000 });
      setUpdate(next);
      setMessage(next ? `${next.version} sürümü hazır.` : "En güncel sürümü kullanıyorsun.");
    } catch {
      setMessage("Güncelleme sunucusuna ulaşılamadı veya henüz bir sürüm yayımlanmadı. Tekrar deneyebilirsin.");
    } finally {
      setBusy(false);
    }
  };
  const install = async () => {
    if (!update) return;
    setBusy(true);
    let downloaded = 0;
    let total = 0;
    try {
      setMessage("Güncelleme indiriliyor…");
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") total = event.data.contentLength ?? 0;
        if (event.event === "Progress") {
          downloaded += event.data.chunkLength;
          setMessage(total ? `İndiriliyor: %${Math.min(100, Math.round(downloaded * 100 / total))}` : "Güncelleme indiriliyor…");
        }
        if (event.event === "Finished") setMessage("İmza doğrulanıyor ve güncelleme kuruluyor…");
      });
      setMessage("Kuruldu. Fusion yeniden başlatılıyor…");
      await relaunch();
    } catch {
      setMessage("Güncelleme tamamlanamadı. Bağlantını ve uygulama klasörüne yazma iznini kontrol edip tekrar dene.");
      setBusy(false);
    }
  };
  return <section className="control-panel__section" aria-label="Uygulama güncellemeleri">
    <h3>Uygulama güncellemeleri</h3>
    <p role="status">{message}</p>
    <p>Kurulum Fusion'ı yeniden başlatır. Önce çalışan görevlerin tamamlanmasını bekle.</p>
    <button type="button" disabled={busy} onClick={() => void inspect()}>Güncellemeleri kontrol et</button>
    {update && <button type="button" disabled={busy} onClick={() => void install()}>İndir, kur ve yeniden başlat</button>}
  </section>;
}
