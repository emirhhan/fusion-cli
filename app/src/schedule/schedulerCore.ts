import { ProtocolClient } from "../protocol/client";
import type { SessionTransport } from "../sessions/types";
import type { ScheduleClient } from "./types";

/**
 * Sohbetsiz zamanlayıcı çekirdeğinin ayrılmış oturum kimliği. Sekme listesinde, kayıtlı
 * görünümde ve geçmişte YER ALMAZ: `useSessions` bu kimliği tanımaz ve satırlarını yok sayar.
 */
export const SCHEDULER_SESSION_ID = "zamanlayici";

/** `zamanlama.*` istekleri yerel dosya işidir; çekirdek susarsa yoklama bu sürede düşer. */
const REQUEST_TIMEOUT_MS = 20_000;

export interface SchedulerCore {
  client: ScheduleClient;
  close(): Promise<void>;
}

/**
 * Hiç sohbet açık değilken vade yoklaması için tek bir görünmez çekirdek süreci açar.
 *
 * Ölçüldü (30 Ekim): yoklama yalnız açık bir sohbetin istemcisine bağlıydı
 * (`pickScheduleClient`); son sohbet kapanınca ya da açılışta sekmeler geri yüklenemeyince
 * uygulama açık olduğu hâlde vadesi gelen görev hiç alınmıyordu (U5-52). Yeni süreç modeli
 * yok: kabuk zaten kimlikle çekirdek açar (`oturum_olustur`); bu yalnız `oturum.baslat`
 * göndermeyen, konuşma/geçmiş kaydı oluşturmayan bir oturumdur.
 *
 * `onClosed`, çekirdek DIŞARIDAN kapanınca (çökme) çağrılır; `close()` ile bilerek
 * kapatmada çağrılmaz.
 */
export async function openSchedulerCore(
  transport: SessionTransport,
  onClosed: (reason: string) => void,
): Promise<SchedulerCore> {
  let handler: (line: string) => void = () => undefined;
  let finished = false;
  const unlisten: (() => void)[] = [];
  const release = () => {
    for (const stop of unlisten.splice(0)) stop();
  };
  const client = new ProtocolClient(
    (line) => {
      void transport.send(SCHEDULER_SESSION_ID, line).catch((reason: unknown) => client.close(String(reason)));
    },
    (next) => {
      handler = next;
    },
  );
  // Dinleyiciler çekirdek açılmadan ÖNCE kurulur: ilk satırlar kaybolmasın.
  unlisten.push(
    await transport.onLine((event) => {
      if (event.oturum_id === SCHEDULER_SESSION_ID) handler(event.satir);
    }),
  );
  unlisten.push(
    await transport.onClosed((event) => {
      if (event.oturum_id !== SCHEDULER_SESSION_ID || finished) return;
      finished = true;
      client.close(event.neden);
      release();
      onClosed(event.neden);
    }),
  );
  try {
    await transport.create(SCHEDULER_SESSION_ID, undefined);
  } catch (reason) {
    finished = true;
    client.close();
    release();
    throw reason;
  }
  return {
    client: { request: (name, data) => client.request(name, data, { timeoutMs: REQUEST_TIMEOUT_MS }) },
    async close() {
      if (finished) return;
      finished = true;
      client.close();
      release();
      await transport.close(SCHEDULER_SESSION_ID).catch(() => undefined);
    },
  };
}
