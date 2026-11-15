import { useEffect, useRef, useState } from "react";
import type { SessionTransport } from "../sessions/types";
import { openSchedulerCore, type SchedulerCore } from "./schedulerCore";
import type { ScheduleClient } from "./types";

/**
 * Açılışta sekmeler geri yüklenirken ikinci bir çekirdek süreci açılmasın: hazır sohbet
 * bu sürede gelmezse (son sohbet kapatılmış, geri yükleme başarısız, çalışma zamanı kurulu
 * değil) görünmez zamanlayıcı çekirdeği açılır.
 */
const DEFAULT_GRACE_MS = 20_000;
/** Açılış başarısızsa ilk yeniden deneme; her başarısızlıkta ikiye katlanır. */
const DEFAULT_RETRY_MS = 60_000;
const MAX_RETRY_MS = 300_000;

interface SchedulerCoreOptions {
  transport: SessionTransport;
  /** Hazır hiçbir sohbet oturumu yok: vade yoklaması için ayrı çekirdek gerekir. */
  needed: boolean;
  graceMs?: number;
  retryMs?: number;
  /** Testler gerçek süreç açmadan çekirdeği taklit eder. */
  open?: (transport: SessionTransport, onClosed: (reason: string) => void) => Promise<SchedulerCore>;
}

/**
 * Sohbet açık değilken de vade yoklamasının çalışması için görünmez çekirdek istemcisi.
 * Hazır sohbet gelince çekirdek kapatılır; yoklama o sohbetin istemcisine geçer
 * (bkz. `pickScheduleClient`). Aynı görevin iki kez verilmemesi çekirdekte garanti edilir
 * (`claim_due` kilit altında atomik; yoklayıcı tek: `zamanlama.sahiplik`).
 */
export function useSchedulerCore({
  transport,
  needed,
  graceMs = DEFAULT_GRACE_MS,
  retryMs = DEFAULT_RETRY_MS,
  open = openSchedulerCore,
}: SchedulerCoreOptions): ScheduleClient | null {
  const [client, setClient] = useState<ScheduleClient | null>(null);
  // Satır içi `open` her render'da yeni kimlik alsa da çalışan çekirdek yeniden kurulmaz.
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    setClient(null);
    if (!needed) return;
    let cancelled = false;
    let core: SchedulerCore | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = retryMs;
    const retryLater = () => {
      if (cancelled) return;
      timer = setTimeout(attempt, delay);
      delay = Math.min(delay * 2, MAX_RETRY_MS);
    };
    const attempt = () => {
      openRef.current(transport, () => {
        core = null;
        setClient(null);
        retryLater();
      }).then(
        (opened) => {
          if (cancelled) {
            void opened.close();
            return;
          }
          core = opened;
          delay = retryMs;
          setClient(opened.client);
        },
        retryLater,
      );
    };
    timer = setTimeout(attempt, graceMs);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
      void core?.close();
    };
  }, [needed, transport, graceMs, retryMs]);
  return needed ? client : null;
}
