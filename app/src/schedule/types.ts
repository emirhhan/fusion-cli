/** Vade yoklaması ve bir makbuz için bekleme aynı mevcut aralığı kullanır. */
export const SCHEDULE_POLL_MS = 30_000;

export interface ScheduleDelivery {
  occurrence_id: string;
  schedule_id: string;
  due_at: number;
  title: string;
  task: string;
  root: string;
  task_id: string | null;
}
export interface ScheduleReceipt {
  occurrenceId: string;
  taskId: string;
  status: "queued";
}
export interface ScheduleDeliveryClient {
  deliver(delivery: ScheduleDelivery): Promise<ScheduleReceipt | null>;
}
export function isScheduleDelivery(value: unknown): value is ScheduleDelivery {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return typeof data.occurrence_id === "string" && /^[a-f0-9]{64}$/.test(data.occurrence_id)
    && typeof data.schedule_id === "string" && data.schedule_id.length > 0
    && typeof data.due_at === "number" && Number.isFinite(data.due_at)
    && typeof data.title === "string" && typeof data.task === "string" && data.task.trim().length > 0
    && typeof data.root === "string" && data.root.trim().length > 0
    && data.task_id === null;
}
export function isScheduleReceipt(value: unknown, occurrenceId: string): value is ScheduleReceipt {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return data.status === "queued" && data.occurrenceId === occurrenceId && data.taskId === `schedule-${occurrenceId}`;
}

export type ScheduleKind = "bir_kez" | "gunluk" | "haftalik" | "aralik";

export interface ScheduledTask {
  baslik: string;
  dakika?: number;
  etkin: boolean;
  gorev: string;
  gunler?: number[];
  id: string;
  kok: string;
  saat?: string;
  son_calisma: number | null;
  son_gecikmeli?: boolean;
  sonraki: number | null;
  tur: ScheduleKind;
  zaman?: number;
}

export interface ScheduleClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

const DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

/** Görevin ne zaman çalıştığını okunur Türkçe ile anlat. */
export function describeSchedule(task: Pick<ScheduledTask, "tur" | "saat" | "gunler" | "dakika" | "zaman">): string {
  if (task.tur === "gunluk") return `Her gün ${task.saat ?? ""}`.trim();
  if (task.tur === "haftalik") {
    const days = [...(task.gunler ?? [])].sort((a, b) => a - b).map((day) => DAYS[day] ?? "?").join(", ");
    return `${days} ${task.saat ?? ""}`.trim();
  }
  if (task.tur === "aralik") {
    const minutes = task.dakika ?? 0;
    return minutes % 60 === 0 ? `${minutes / 60} saatte bir` : `${minutes} dakikada bir`;
  }
  return task.zaman ? `Bir kez · ${formatMoment(task.zaman)}` : "Bir kez";
}

export function formatMoment(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("tr-TR", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export const DAY_LABELS = DAYS;
