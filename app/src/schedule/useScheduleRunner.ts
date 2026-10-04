import { useEffect, useRef } from "react";
import type { ScheduleClient, ScheduledTask } from "./types";

/** Vadesi gelen görevleri yoklama aralığı. Dakika hassasiyeti yeterli; daha sık
 * yoklama çekirdeği boşuna meşgul eder. */
export const SCHEDULE_POLL_MS = 30_000;

interface RunnerSession {
  status: string;
}

interface ScheduleRunnerInput {
  client: ScheduleClient | null;
  create: (input: { mode: "kod"; root: string; title: string }) => Promise<string>;
  send: (id: string, task: string) => boolean;
  sessions: Record<string, RunnerSession | undefined>;
  onStarted?: (task: ScheduledTask) => void;
}

interface Pending {
  sessionId: string;
  task: ScheduledTask;
}

/** Zamanı gelen görev için yeni bir sohbet açar ve görevi ona gönderir.
 *
 * Çekirdek görevi verirken takvimi ilerlettiği için aynı görev iki kez gelmez.
 * Oturum açılır açılmaz "hazır" olmaz; görev, oturum hazır olana kadar bekletilir. */
export function useScheduleRunner({ client, create, send, sessions, onStarted }: ScheduleRunnerInput) {
  const pending = useRef<Pending[]>([]);
  const createRef = useRef(create);
  createRef.current = create;

  useEffect(() => {
    if (!client) return;
    let active = true;
    const poll = async () => {
      try {
        const result = await client.request("zamanlama.vadesi_gelenler", {});
        const due = result.ok && Array.isArray(result.gorevler) ? (result.gorevler as ScheduledTask[]) : [];
        for (const task of due) {
          if (!active) return;
          const sessionId = await createRef.current({ mode: "kod", root: task.kok, title: task.baslik });
          pending.current = [...pending.current, { sessionId, task }];
        }
      } catch {
        // Çekirdek meşgul ya da kapanıyor: görev alınmadıysa takvimi ilerlemedi,
        // bir sonraki yoklamada yeniden denenir.
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), SCHEDULE_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [client]);

  useEffect(() => {
    if (pending.current.length === 0) return;
    pending.current = pending.current.filter(({ sessionId, task }) => {
      if (sessions[sessionId]?.status !== "ready") return true;
      if (!send(sessionId, task.gorev)) return true;
      onStarted?.(task);
      return false;
    });
  }, [onStarted, send, sessions]);

  return {
    /** "Şimdi çalıştır": görevi takvimi beklemeden aynı yoldan başlatır. */
    async runNow(task: ScheduledTask) {
      const sessionId = await createRef.current({ mode: "kod", root: task.kok, title: task.baslik });
      pending.current = [...pending.current, { sessionId, task }];
    },
  };
}
