import { useEffect, useRef } from "react";
import type { ProtocolClient } from "../protocol/client";
import { hydratePrefs, installPrefsMirror } from "./prefsMirror";

type Client = Pick<ProtocolClient, "request">;

/**
 * Tercihler çekirdekte de yedeklenir (webview deposu güvenilmez). Çekirdek yerel
 * depodan farklı bir değer getirdiyse açık ekranlar eski değeri okumuş olur; bu
 * yüzden pencere bir kez yenilenir (oturumlar geri yüklenir).
 *
 * Ölçüldü (29 Ekim): ayna ilk istemciye kuruluyor ama temizleme işlevi
 * `activeClient` değişince çalışıyordu; `mirroredClient` dolu olduğundan efekt
 * yeniden kurmadan dönüyor, ikinci sohbete geçince yedekleme sessizce
 * duruyordu. Ayna artık bir kez kurulur, yalnız bileşen sökülürken kaldırılır;
 * yazmalar her zaman GÜNCEL istemciden gider.
 */
export function usePrefsMirror(activeClient: Client | undefined): void {
  const hydrated = useRef(false);
  const latestClient = useRef(activeClient);
  latestClient.current = activeClient;
  const closed = useRef(false);
  const restore = useRef<(() => void) | undefined>(undefined);
  const target = useRef<Client>({
    request: (name, data) => latestClient.current
      ? latestClient.current.request(name, data)
      : Promise.reject(new Error("Fusion oturumu yok.")),
  }).current;

  useEffect(() => {
    if (!activeClient || hydrated.current) return;
    hydrated.current = true;
    void hydratePrefs(activeClient).then((changed) => {
      if (closed.current) return;
      restore.current = installPrefsMirror(target);
      let reloaded = false;
      try { reloaded = sessionStorage.getItem("fusion.prefs-reloaded") === "1"; } catch { /* Depo yoksa tek yenileme riski. */ }
      if (changed && !reloaded) {
        try { sessionStorage.setItem("fusion.prefs-reloaded", "1"); } catch { return; }
        window.location.reload();
      }
    }).catch((error: unknown) => console.error("Arayüz tercihleri çekirdekten okunamadı", error));
  }, [activeClient, target]);

  useEffect(() => {
    closed.current = false;
    return () => {
      closed.current = true;
      restore.current?.();
      restore.current = undefined;
    };
  }, []);
}
