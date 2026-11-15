import { useEffect, useRef } from "react";
import { startKitsWithTauri, type StartKits } from "./startKits";

/** Kits yan sürecini, kullanıcı Kits'e girmeden arka planda başlatır.
 *
 * Ölçüldü (31 Ekim, paketli 0.7.19, M1): Kits sunucusu ancak Fusion model geçidi
 * (`fusion serve`) sağlıklı olunca dinlemeye başlıyor; Kits'e ilk girişte 1,1-5,3 sn
 * "hazırlanıyor" bekleniyordu (geçitsiz sunucu 0,2 sn). Çekirdek oturumu kurulunca
 * (çalışma zamanı hazır, `kits_baslat` çekirdek yolunu bulabilir) bir kez denenir.
 * İki çekirdek açılışı aynı anda birbirini yavaşlatmıyor (tek 0,69-0,91 sn, eşzamanlı
 * iki 0,74-0,81 sn). Maliyet: açılışta ~140 MB Node + ~118 MB geçit RSS, boşta %0 CPU.
 * Başarısızsa Kits ekranı kendi denemesini yapar ve hatayı orada gösterir. */
export function useKitsPrewarm(coreReady: boolean, start: StartKits = startKitsWithTauri): void {
  const started = useRef(false);
  useEffect(() => {
    if (!coreReady || started.current) return;
    started.current = true;
    start().catch((error: unknown) => {
      console.warn("Kits ön başlatması tamamlanamadı; Kits ekranı yeniden deneyecek.", error);
    });
  }, [coreReady, start]);
}
