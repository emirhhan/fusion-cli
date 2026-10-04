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
