import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { onRemoteInUseChange, remoteInUse } from "./remoteFlag";

/**
 * Sohbet başlığındaki "Uzaktan kontrol" anahtarının verisi (P-066).
 *
 * Claude Code sohbet başlığında Remote Control durumunu gösterir; Fusion'da bu bilgi
 * yalnız Ayarlar › Uzaktan Erişim'in içindeydi. Yoklama YALNIZ uzaktan erişimi bir kez
 * kurmuş kullanıcıda çalışır (`remoteInUse`): kurmamış kullanıcıda `uzak.*` isteği hiç
 * atılmaz, anahtar "kapalı" görünür ve tıklanınca kurulum ekranına götürür. Bayrak oturum
 * içinde değişirse (`markRemoteInUse`) yoklama yeniden başlatmasız açılır/kapanır.
 */

export interface RemoteStatus {
  /** `uzak.durum` okunabildi mi? Okunamadıysa anahtar yine çizilir ama sayılar bilinmez. */
  known: boolean;
  listening: boolean;
  deviceCount: number;
  pendingApprovals: number;
}

export const KAPALI: RemoteStatus = { known: false, listening: false, deviceCount: 0, pendingApprovals: 0 };

/** Yoklama aralığı: başlık anlık değil, yaklaşık bilgi verir; ayrıntı Ayarlar'da. */
export const UZAK_DURUM_YOKLAMA_MS = 20_000;

export function useRemoteStatus(client: ProtocolClient | null): RemoteStatus {
  const [status, setStatus] = useState<RemoteStatus>(KAPALI);
  const [inUse, setInUse] = useState<boolean>(remoteInUse);

  useEffect(() => onRemoteInUseChange(setInUse), []);

  const load = useCallback(async () => {
    if (!client || !remoteInUse()) return;
    try {
      const durum = (await client.request("uzak.durum", {})) as {
        ok?: boolean; dinliyor?: boolean; cihazSayisi?: number;
      };
      if (durum?.ok === false) return;
      const bekleyen = (await client.request("uzak.bekleyen", {})) as { sorular?: unknown[] };
      setStatus({
        known: true,
        listening: Boolean(durum?.dinliyor),
        deviceCount: Number(durum?.cihazSayisi ?? 0),
        pendingApprovals: Array.isArray(bekleyen?.sorular) ? bekleyen.sorular.length : 0,
      });
    } catch {
      // Sessiz: başlık göstergesi bir kolaylıktır; hata Ayarlar ekranında görünür.
    }
  }, [client]);

  useEffect(() => {
    if (!client || !inUse) {
      setStatus(KAPALI);
      return;
    }
    void load();
    const timer = window.setInterval(() => void load(), UZAK_DURUM_YOKLAMA_MS);
    // Pencereye dönüldüğünde hemen yenile: telefon bu arada eşleşmiş olabilir.
    window.addEventListener("focus", load);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, [client, inUse, load]);

  return status;
}
