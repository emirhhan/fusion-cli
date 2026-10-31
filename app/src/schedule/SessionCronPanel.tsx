import { useCallback, useEffect, useState } from "react";
import { Icon } from "../ui/Icon";
import { formatMoment } from "./types";
import { SESSION_CRON_POLL_MS } from "./useSessionCron";

interface CronClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

/** `cron.listele` satırı (çekirdekte `CronTask.to_dict`). */
export interface SessionCronTask {
  id: string;
  prompt: string;
  kind: string;
  next_due: number;
  every_s: number;
  cron: string;
  runs: number;
  source: string;
}

function parseTask(value: unknown): SessionCronTask | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.id !== "string" || typeof raw.prompt !== "string" || typeof raw.next_due !== "number") return null;
  return {
    id: raw.id,
    prompt: raw.prompt,
    kind: typeof raw.kind === "string" ? raw.kind : "",
    next_due: raw.next_due,
    every_s: typeof raw.every_s === "number" ? raw.every_s : 0,
    cron: typeof raw.cron === "string" ? raw.cron : "",
    runs: typeof raw.runs === "number" ? raw.runs : 0,
    source: raw.source === "ajan" ? "ajan" : "kullanici",
  };
}

const UNITS: Array<[number, string]> = [[86400, "gün"], [3600, "saat"], [60, "dk"]];

/** Görevin zamanlamasını tek kısa ifadeye çevir (çekirdekteki `describe` ile aynı dil). */
export function describeSessionCron(task: SessionCronTask): string {
  if (task.kind === "aralik" && task.every_s > 0) {
    const [size, label] = UNITS.find(([unit]) => task.every_s % unit === 0) ?? [1, "sn"];
    return `Her ${task.every_s / size} ${label}`;
  }
  if (task.kind === "cron" && task.cron) return `Cron ${task.cron}`;
  // Aralıksız `/loop <görev>`: sıradaki çalışmayı ajan seçer (P-038).
  if (task.kind === "kendi_tempolu") return "Kendi tempolu";
  return "Bir kez";
}

/**
 * Etkin sohbetin oturum zamanlayıcısı (`/loop`, `cron_create`, `schedule_wakeup`) — P-038.
 *
 * Kalıcı Zamanlananlar'dan ayrıdır: görevler bu sohbetle yaşar, en çok 7 gün. Terminaldeki
 * `/loop list` / `/loop stop` karşılığı; ölçüldü (31 Ekim): masaüstünde `cron.listele`'yi
 * kullanan hiçbir yüzey yoktu.
 */
export function SessionCronPanel({ client, visible = true, pollMs = SESSION_CRON_POLL_MS }: { client: CronClient | null; visible?: boolean; pollMs?: number }) {
  const [tasks, setTasks] = useState<SessionCronTask[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!client) return;
    try {
      const result = await client.request("cron.listele", {});
      const list = Array.isArray(result.gorevler) ? result.gorevler.map(parseTask).filter((task): task is SessionCronTask => task !== null) : [];
      setTasks(list);
      setError(null);
    } catch {
      setError("Sohbet döngüleri okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    if (!client || !visible) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), pollMs);
    return () => window.clearInterval(timer);
  }, [client, visible, pollMs, refresh]);

  const stop = async (id: string) => {
    if (!client) return;
    let failure: string | null = null;
    try {
      const result = await client.request("cron.sil", { id });
      if (result.ok !== true) failure = typeof result.metin === "string" ? result.metin : "Görev durdurulamadı.";
    } catch {
      failure = "Görev durdurulamadı.";
    }
    // Liste yenilenir; durdurma hatası yenilemeden sonra yazılır ki silinmesin.
    await refresh();
    if (failure) setError(failure);
  };

  if (!client) return null;
  return (
    <section aria-labelledby="session-cron-heading" className="session-cron">
      <h2 id="session-cron-heading">Bu sohbetin döngüleri</h2>
      {error && <p className="schedule__error" role="alert">{error}</p>}
      {tasks.length === 0 ? (
        <p className="schedule__hint">Döngü yok. Sohbete <code>/loop 10m &lt;görev&gt;</code> yaz.</p>
      ) : (
        <ul aria-label="Sohbet döngüleri">
          {tasks.map((task) => (
            <li className="session-cron__item" key={task.id}>
              <span className="session-cron__body">
                <span className="session-cron__prompt" title={task.prompt}>{task.prompt}</span>
                <span className="session-cron__meta">
                  <Icon name="clock" size={12} /> {describeSessionCron(task)} · sıradaki {formatMoment(task.next_due)}
                  {task.source === "ajan" ? " · ajan kurdu" : ""}
                </span>
              </span>
              <button aria-label={`${task.prompt} döngüsünü durdur`} className="session-cron__stop" onClick={() => void stop(task.id)} type="button">Durdur</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
