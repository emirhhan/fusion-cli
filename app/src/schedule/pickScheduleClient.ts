import type { ScheduleClient } from "./types";

interface ClientSession {
  client: ScheduleClient;
  status: string;
}

/**
 * Vade yoklaması için çekirdek istemcisi seçer. Zamanlama deposu kullanıcı
 * düzeyinde TEK dosyadır; her çekirdek süreci aynı kuyruğu görür, bu yüzden
 * hazır herhangi bir oturum yeterlidir. Ölçüldü (29 Ekim): yoklama yalnız
 * etkin sohbetin istemcisine bağlıydı; etkin sohbet kapanınca ya da çökünce
 * açık duran diğer sohbetler varken bile vadesi gelen görev alınmıyordu.
 * Etkin oturum hazırsa o seçilir (gereksiz yoklama yeniden kurulumu olmaz).
 */
export function pickScheduleClient(
  active: ClientSession | null | undefined,
  sessions: readonly ClientSession[],
): ScheduleClient | null {
  if (active?.status === "ready") return active.client;
  return sessions.find((session) => session.status === "ready")?.client ?? null;
}
