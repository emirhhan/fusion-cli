import { useEffect, useRef } from "react";
import { submissionAccepted, type SubmissionResult } from "../sessions/submission";

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

/** Görevi kim kurdu: kullanıcı (`/loop`) ya da ajan (`cron_create`, `schedule_wakeup`). */
export type CronSource = "kullanici" | "ajan";

export interface FiredCronTask {
  id: string;
  gorev: string;
}

/** Gönderim sonucu: `false` ya da reddedilen makbuz görevin geri verilmesini ister. */
export type CronSendResult = SubmissionResult | Promise<SubmissionResult>;

/**
 * Oturum zamanlayıcısı (`/loop`, `cron_create`, `schedule_wakeup`) için vade yoklaması (P-038).
 *
 * Çekirdek vadesi gelen görevi yalnız tur sürmüyorken verir ve aynı görevi iki kez vermez
 * (`cron.vadesi_gelenler`); arayüz onu normal gönderim yolundan tur olarak başlatır. Böylece
 * zamanlanmış tur da sohbette kullanıcı mesajı gibi görünür ve aynı onay akışından geçer.
 * Kaynak `send`'e iletilir: kullanıcının kurduğu ve modelin çağırabildiği beceri komut olarak,
 * ajanın kurduğu satır ve `duz_metin` işaretli satır (`/verify`, `/model`…) düz tur olarak gider. Gönderim reddedilirse görev `cron.geri_ver`
 * ile çekirdeğe geri verilir; ölçüldü (31 Ekim): dönüş değeri denetlenmiyor, vade boşa gidiyordu.
 */
export function useSessionCron({
  session,
  send,
  onFired,
  pollMs = SESSION_CRON_POLL_MS,
}: {
  session: CronSession | null;
  send: (id: string, task: string, source: CronSource) => CronSendResult;
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
          const task = item as {
            id?: unknown;
            gorev?: unknown;
            kaynak?: unknown;
            duz_metin?: unknown;
          };
          if (typeof task.gorev !== "string" || !task.gorev.trim()) continue;
          const taskId = typeof task.id === "string" ? task.id : "";
          onFired?.({ id: taskId, gorev: task.gorev });
          // Eski çekirdek kaynak göndermez: o görevler yalnız `/loop` ile kurulabiliyordu.
          // Claude (#371): yalnız modelin çağırabildiği beceri komut olur; çekirdek gerisini
          // `duz_metin` ile işaretler ve satır ajanın satırı gibi düz tur gider.
          const plainText = task.duz_metin === true;
          const source: CronSource = task.kaynak === "ajan" || plainText ? "ajan" : "kullanici";
          let accepted = false;
          try {
            accepted = submissionAccepted(await send(id, task.gorev, source));
          } catch {
            accepted = false;
          }
          if (!accepted && taskId) await client.request("cron.geri_ver", { id: taskId });
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
