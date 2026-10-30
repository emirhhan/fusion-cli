import { isTauri } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

const reasonText = (reason: unknown): string => (reason instanceof Error ? reason.message : String(reason));
/** İmza/doğrulama hatası ağ hatasından ayrı söylenir: kullanıcı kurulumun GÜVENLİK nedeniyle durduğunu bilmeli. */
const isSignatureError = (text: string): boolean => /signature|imza|verif|doğrula/i.test(text);

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
    } catch (reason) {
      setMessage(`Güncelleme sunucusuna ulaşılamadı veya henüz bir sürüm yayımlanmadı (${reasonText(reason)}). Tekrar deneyebilirsin.`);
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
    } catch (reason) {
      const text = reasonText(reason);
      setMessage(isSignatureError(text)
        ? "Güncelleme tamamlanamadı: imza doğrulanamadığı için kurulum yapılmadı."
        : `Güncelleme tamamlanamadı (${text}). Bağlantını ve uygulama klasörüne yazma iznini kontrol edip tekrar dene.`);
      setBusy(false);
      return;
    }
    // Kurulum bitti; yeniden başlatma ayrı hata verebilir ve "tamamlanamadı" demek yanlış olur.
    try {
      setMessage("Kuruldu. Fusion yeniden başlatılıyor…");
      await relaunch();
    } catch {
      setMessage("Güncelleme kuruldu ama Fusion yeniden başlatılamadı. Uygulamayı kapatıp elle yeniden aç.");
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
