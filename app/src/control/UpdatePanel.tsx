import { isTauri } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

const reasonText = (reason: unknown): string => (reason instanceof Error ? reason.message : String(reason));
/** İmza/doğrulama hatası ağ hatasından ayrı söylenir: kullanıcı kurulumun GÜVENLİK nedeniyle durduğunu bilmeli. */
const isSignatureError = (text: string): boolean => /signature|imza|verif|doğrula/i.test(text);

/** `turnRunning`: çalışan bir görev varken kurulum kapalıdır (yeniden başlatma görevi keser). */
export function UpdatePanel({ turnRunning = false }: { turnRunning?: boolean } = {}) {
  const [update, setUpdate] = useState<Update | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Yeni sürümü kontrol edebilirsin.");
  /** Sürüm notları (P-066): manifestin `notes` alanı; güncelleyici `body` olarak taşır. Düz metin olarak çizilir. */
  const [notes, setNotes] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  useEffect(() => () => { void update?.close().catch(() => undefined); }, [update]);
  useEffect(() => {
    if (!isTauri()) return;
    let alive = true;
    // Kurulu sürüm kabuktan okunur; okunamazsa satır çizilmez (uydurma sürüm yok).
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then((version) => { if (alive) setCurrentVersion(version); })
      .catch(() => undefined);
    return () => { alive = false; };
  }, []);
  if (!isTauri()) return null;

  const inspect = async () => {
    setBusy(true);
    setMessage("Güncelleme kontrol ediliyor…");
    try {
      const next = await check({ timeout: 15000 });
      setUpdate(next);
      setNotes(next?.body?.trim() ? next.body.trim() : null);
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
    {currentVersion && <p className="control-panel__meta">Kurulu sürüm: {currentVersion} · kanal: kararlı (GitHub Releases, imzalı)</p>}
    <p role="status">{message}</p>
    <p>Kurulum Fusion'ı yeniden başlatır. Önce çalışan görevlerin tamamlanmasını bekle.</p>
    {turnRunning && <p role="alert">Çalışan bir görev var; kurulum görev bitene kadar kapalı.</p>}
    <button type="button" disabled={busy} onClick={() => void inspect()}>Güncellemeleri kontrol et</button>
    {update && <button type="button" disabled={busy || turnRunning} onClick={() => void install()}>İndir, kur ve yeniden başlat</button>}
    {update && notes && (
      <details className="control-panel__notes" open>
        <summary>Sürüm notları · {update.version}</summary>
        {/* Düz metin: manifestteki `notes` HTML olarak yorumlanmaz. */}
        <pre>{notes}</pre>
      </details>
    )}
  </section>;
}
