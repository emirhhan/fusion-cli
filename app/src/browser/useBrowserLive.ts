import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { BROWSER_RPC, FRAME_POLL_MS, decodeSnapshot, type BrowserFrame, type BrowserSnapshot } from "./browserPanelProtocol";

/**
 * Paylaşılan tarayıcının canlı görüntüsünü çeker (P-045).
 *
 * Panel görünürken her `FRAME_POLL_MS`'de `tarayici_panel.kare` istenir; çekirdek yalnız sayfa
 * değişince yeni kare verir (`son` ile), yoksa yalnız durum döner. İstekler üst üste binmez:
 * bir sonraki çekim öncekinin cevabından sonra planlanır. Panel kapanınca (bileşen sökülünce)
 * çekim durur; çekirdek kare onayı almadığı için tarayıcı da kare üretmeyi bırakır.
 */
export interface BrowserLive {
  snapshot: BrowserSnapshot | null;
  frame: BrowserFrame | null;
  error: string | null;
  refresh: () => void;
}

export function useBrowserLive(client: ProtocolClient): BrowserLive {
  const [snapshot, setSnapshot] = useState<BrowserSnapshot | null>(null);
  const [frame, setFrame] = useState<BrowserFrame | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const wake = useRef<() => void>(() => undefined);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      timer = undefined;
      try {
        const payload = await client.request(`${BROWSER_RPC}kare`, { son: seq.current });
        if (!alive) return;
        if (payload.ok === false) {
          setError(typeof payload.metin === "string" ? payload.metin : "Tarayıcı görüntüsü alınamadı.");
        } else {
          const next = decodeSnapshot(payload);
          setError(null);
          setSnapshot(next);
          if (!next.acik) {
            seq.current = 0;
            setFrame(null);
          } else if (next.kare) {
            seq.current = next.seq;
            setFrame(next.kare);
          }
        }
      } catch (reason) {
        if (!alive) return;
        setError(reason instanceof Error ? reason.message : "Tarayıcı görüntüsü alınamadı.");
      }
      if (alive) timer = window.setTimeout(() => void tick(), FRAME_POLL_MS);
    };
    wake.current = () => {
      if (timer === undefined) return;
      window.clearTimeout(timer);
      void tick();
    };
    void tick();
    return () => {
      alive = false;
      if (timer !== undefined) window.clearTimeout(timer);
      wake.current = () => undefined;
    };
  }, [client]);

  const refresh = useCallback(() => wake.current(), []);
  return { snapshot, frame, error, refresh };
}
