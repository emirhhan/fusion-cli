import { useEffect, useState } from "react";

/**
 * Arka planda bir kez güncelleme kontrolü.
 *
 * Kullanıcı güncellemeyi ARAMAK zorunda kalmamalı: eskiden yeni sürüm ancak
 * Kontrol Paneli açılıp "Güncellemeleri kontrol et" düğmesine basılırsa
 * görünüyordu ve kimse oraya bakmıyordu. Sürüm çıktığında kenar çubuğunda ince
 * bir şerit belirir.
 *
 * Kontrol SESSİZDİR: ağ yoksa, sunucuya ulaşılamıyorsa ya da uygulama kabuk
 * dışında çalışıyorsa hiçbir şey gösterilmez. Bir hata mesajı, kullanıcının
 * istemediği bir işin başarısızlığını bildirirdi.
 */

/** Kontrol için tanınan süre (ms). Açılışı geciktirmeyecek kadar kısa. */
const TIMEOUT_MS = 15_000;
/** Uzun süre açık kalan uygulama yeni sürümü görsün diye periyodik yeniden kontrol (U5-44). */
export const YENIDEN_KONTROL_MS = 6 * 60 * 60 * 1000;

export function useUpdateAvailable(): string | null {
  const [surum, setSurum] = useState<string | null>(null);

  useEffect(() => {
    let gecerli = true;
    const kontrolEt = async () => {
      try {
        const { isTauri } = await import("@tauri-apps/api/core");
        if (!isTauri()) return;
        const { check } = await import("@tauri-apps/plugin-updater");
        const sonuc = await check({ timeout: TIMEOUT_MS });
        if (gecerli && sonuc?.version) setSurum(sonuc.version);
        // Nesne kapatılır: açık kalan indirme tutamacı sızdırırdı.
        await sonuc?.close().catch(() => undefined);
      } catch {
        // Sessiz: kullanıcı bu işi istemedi, başarısızlığını da duymamalı.
      }
    };
    void kontrolEt();
    const zamanlayici = window.setInterval(() => void kontrolEt(), YENIDEN_KONTROL_MS);
    return () => {
      gecerli = false;
      window.clearInterval(zamanlayici);
    };
  }, []);

  return surum;
}
