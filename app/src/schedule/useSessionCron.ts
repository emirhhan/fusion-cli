import { useEffect, useRef } from "react";

/** Vade yoklaması; görevler en az 1 dakikalık olduğundan 15 sn yeter. */
export const SESSION_CRON_POLL_MS = 15_000;

interface CronSession {
  id: string;
  status: string;
  running: boolean;
  /** Onay/soru bekleyen kart: kullanıcı cevap vermeden zamanlanmış görev araya girmez. */
  question?: unknown;
  client?: { request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>> } | null;
}

export interface FiredCronTask {
  id: string;
  gorev: string;
}

/**
 * Oturum zamanlayıcısı (`/loop`, `cron_create`, `schedule_wakeup`) için vade yoklaması (P-038).
 *
 * Çekirdek vadesi gelen görevi yalnız tur sürmüyorken verir ve aynı görevi iki kez vermez
 * (`cron.vadesi_gelenler`); arayüz onu normal gönderim yolundan tur olarak başlatır. Böylece
 * zamanlanmış tur da sohbette kullanıcı mesajı gibi görünür ve aynı onay akışından geçer.
 */
export function useSessionCron({
  session,
  send,
  onFired,
  pollMs = SESSION_CRON_POLL_MS,
}: {
  session: CronSession | null;
  send: (id: string, task: string) => boolean;
  onFired?: (task: FiredCronTask) => void;
  pollMs?: number;
}): void {
  // Çalışma/soru durumu her render'da değişir; aralık yeniden kurulmasın diye ref'te tutulur.
  const live = useRef({ running: false, question: null as unknown });
  live.current = { running: Boolean(session?.running), question: session?.question ?? null };
  const client = session?.client ?? null;
  const id = session?.id ?? null;
  const ready = session?.status === "ready";

  useEffect(() => {
    if (!client || !id || !ready) return;
    let busy = false;
    const poll = async () => {
      if (busy || live.current.running || live.current.question) return;
      busy = true;
      try {
        const result = await client.request("cron.vadesi_gelenler", {});
        const gorevler = Array.isArray(result.gorevler) ? (result.gorevler as unknown[]) : [];
        for (const item of gorevler) {
          const task = item as { id?: unknown; gorev?: unknown };
          if (typeof task.gorev !== "string" || !task.gorev.trim()) continue;
          onFired?.({ id: typeof task.id === "string" ? task.id : "", gorev: task.gorev });
          send(id, task.gorev);
          break;
        }
      } catch {
        // Yoklama hatası sessiz kalır: görev çekirdekte durur, sonraki yoklamada gelir.
      } finally {
        busy = false;
      }
    };
    const timer = window.setInterval(() => void poll(), pollMs);
    return () => window.clearInterval(timer);
  }, [client, id, ready, send, onFired, pollMs]);
}
