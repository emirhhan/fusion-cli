import { useEffect, useRef, useState } from "react";
import {
  SCHEDULE_POLL_MS,
  isScheduleDelivery,
  isScheduleReceipt,
  type ScheduleClient,
  type ScheduledTask,
  type ScheduleDeliveryClient,
} from "./types";
import { schedulerOwnerId } from "./schedulerOwner";
export { SCHEDULE_POLL_MS } from "./types";

/** Kira, yoklama aralığının 2,5 katı: bir yoklama kaçsa da sahip kalır, çökerse çabuk devredilir. */
const LEASE_SECONDS = (SCHEDULE_POLL_MS * 2.5) / 1000;

interface RunnerSession {
  status: string;
  running?: boolean;
  client?: { request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>> };
  /** Onay/soru bekleyen kart; zamanlanmış tur bunda askıda bekler. */
  question?: { id: string; data: { arac?: string; baslik?: string; soru?: string } } | null;
}

/** Zamanlanmış tur onay gerektiren bir araca takıldı: kullanıcı yokken ilerlemez, bildirilir (U5-57). */
export interface ScheduleApprovalNotice {
  task: ScheduledTask;
  sessionId: string;
  /** Onay isteyen aracın adı ya da kısa başlığı. */
  tool: string;
}

interface ScheduleRunnerInput {
  client: ScheduleClient | null;
  create: (input: {
    mode: "kod";
    root: string;
    title: string;
  }) => Promise<string>;
  send: (id: string, task: string) => boolean;
  sessions: Record<string, RunnerSession | undefined>;
  deliveryClient?: ScheduleDeliveryClient | null;
  onStarted?: (task: ScheduledTask) => void;
  onNeedsApproval?: (notice: ScheduleApprovalNotice) => void;
  /** Görev güvenli biçimde başlatılamadı (izin modu doğrulanamadı); gönderilmedi. */
  onBlocked?: (task: ScheduledTask, reason: string) => void;
}

interface Watched {
  task: ScheduledTask;
  notified: Set<string>;
  sawRunning: boolean;
}

interface Pending {
  sessionId: string;
  task: ScheduledTask;
}

/** Aynı geçersiz kayıt her yoklamada günlüğü doldurmasın. */
const gecersizBildirilen = new Set<string>();

/**
 * Yoklamayı aynı anda tek uygulama örneği yapar: aynı bekleyen teslimi iki örnek birlikte
 * Kits'e gönderirdi. Yalnız açık "başkasında" yanıtı yoklamayı atlatır; eski çekirdek
 * (bilinmeyen istek) ya da okunamayan yanıt eskisi gibi sürer, çünkü teslimler ack'e kadar
 * çekirdekte kalır ve Kits aynı vadeyi tek kez kuyruğa alır.
 */
async function holdsPollingLease(client: ScheduleClient): Promise<boolean> {
  const result = await client.request("zamanlama.sahiplik", { sahip: schedulerOwnerId(), sure_s: LEASE_SECONDS });
  return !(result.ok === true && result.sahip === false);
}

async function deliverPending(
  client: ScheduleClient,
  deliveryClient: ScheduleDeliveryClient | null | undefined,
  inFlight: Set<string>,
  active: () => boolean,
) {
  await client.request("zamanlama.vadesi_gelenler", {});
  const result = await client.request("zamanlama.teslim_bekleyenler", {});
  if (
    !active() ||
    !deliveryClient ||
    result.ok !== true ||
    !Array.isArray(result.teslimler)
  )
    return;
  const seen = new Set<string>();
  // Biçimi geçersiz teslim her yoklamada yeniden gelir ve sessizce atlanırdı; en az bir kez günlüğe yazılır (U5-53).
  for (const raw of result.teslimler) {
    if (isScheduleDelivery(raw)) continue;
    const kimlik = String((raw as { occurrence_id?: unknown } | null)?.occurrence_id ?? "?");
    if (!gecersizBildirilen.has(kimlik)) {
      gecersizBildirilen.add(kimlik);
      console.warn(`Zamanlama teslimi geçersiz biçimde, atlandı: ${kimlik}`);
    }
  }
  for (const delivery of result.teslimler.filter(isScheduleDelivery)) {
    if (!active()) break;
    if (
      seen.has(delivery.occurrence_id) ||
      inFlight.has(delivery.occurrence_id)
    )
      continue;
    seen.add(delivery.occurrence_id);
    inFlight.add(delivery.occurrence_id);
    try {
      const receipt = await deliveryClient.deliver(delivery);
      if (active() && isScheduleReceipt(receipt, delivery.occurrence_id)) {
        await client.request("zamanlama.teslim_onayla", {
          occurrence_id: delivery.occurrence_id,
          task_id: receipt.taskId,
        });
      }
    } catch {
      // Ölçüldü (29 Ekim): tek teslimin istisnası döngüyü bitiriyor ve hep aynı
      // kayıt sırada başta kaldığı için arkasındaki teslimleri sonsuza dek
      // bekletiyordu. Ack'siz kayıt çekirdekte kalır; sonraki yoklamada tekrar
      // denenir, sıradaki teslim bu turda ilerler.
    } finally {
      inFlight.delete(delivery.occurrence_id);
    }
  }
}
function startDeliveryPolling(
  client: ScheduleClient,
  deliveryClient: ScheduleDeliveryClient | null | undefined,
  polling: { current: boolean },
  inFlight: Set<string>,
) {
  let active = true;
  const poll = async () => {
    if (polling.current) return;
    polling.current = true;
    try {
      if (!(await holdsPollingLease(client))) return;
      await deliverPending(client, deliveryClient, inFlight, () => active);
    } catch {
      // Makbuz veya ack yoksa çekirdeğin kalıcı teslim kaydı sonraki yoklamada kalır.
    } finally {
      polling.current = false;
    }
  };
  void poll();
  const timer = window.setInterval(() => void poll(), SCHEDULE_POLL_MS);
  // Uygulama kapanırken kira hemen bırakılır; yoksa yeniden açılış süre dolana kadar bekler.
  // İstemci değişiminde BIRAKILMAZ: iki çekirdek arasında sıra garantisi yok, kira kaçabilir.
  const release = () => void client.request("zamanlama.sahiplik_birak", { sahip: schedulerOwnerId() }).catch(() => undefined);
  window.addEventListener("pagehide", release);
  return () => {
    active = false;
    window.clearInterval(timer);
    window.removeEventListener("pagehide", release);
  };
}

/**
 * Gözetimsiz tur "İzinleri atla" ile çalışmamalı: hiçbir şey sormaz, kullanıcı yokken
 * onay gerektiren iş sessizce yapılırdı. Yeni oturum kullanıcının kalıcı modunu devralır;
 * bypass ise YALNIZ bu oturum için "auto"ya çekilir (`mod_kalici:false`: kullanıcının
 * varsayılanı config'e yazılıp bozulmaz). Mod okunamazsa güvenli tarafta kalınır (U5-57).
 */
async function ensureUnattendedSafe(client: NonNullable<RunnerSession["client"]>): Promise<void> {
  const state = await client.request("oturum.durum", {});
  if (state.ok === false) throw new Error("izin modu okunamadı");
  if (state.mod !== "bypass") return;
  const changed = await client.request("oturum.baslat", { mod: "auto", mod_kalici: false });
  if (changed.ok === false) throw new Error("izin modu değiştirilemedi");
}

/** Otomatik vadeler kalıcı Kits kuyruğuna teslim edilir; manuel yol sohbet açar. */
export function useScheduleRunner({
  client,
  create,
  send,
  sessions,
  onStarted,
  onNeedsApproval,
  onBlocked,
  deliveryClient,
}: ScheduleRunnerInput) {
  const pending = useRef<Pending[]>([]);
  const createRef = useRef(create);
  createRef.current = create;
  const guards = useRef(new Map<string, "checking" | "ok">());
  const watched = useRef(new Map<string, Watched>());
  const [guardTick, setGuardTick] = useState(0);
  const callbacks = useRef({ onNeedsApproval, onBlocked });
  callbacks.current = { onNeedsApproval, onBlocked };

  const polling = useRef(false);
  const inFlight = useRef(new Set<string>());
  useEffect(() => {
    if (!client) return;
    return startDeliveryPolling(
      client,
      deliveryClient,
      polling,
      inFlight.current,
    );
  }, [client, deliveryClient]);

  useEffect(() => {
    // Başlayan zamanlanmış turlar: onay isteyen araçta tur askıda bekler, kullanıcı bilgilendirilir.
    for (const [sessionId, watch] of watched.current) {
      const session = sessions[sessionId];
      if (!session || session.status === "crashed" || session.status === "closed") {
        watched.current.delete(sessionId);
        continue;
      }
      if (session.running) watch.sawRunning = true;
      const question = session.question;
      if (question && !watch.notified.has(question.id)) {
        watch.notified.add(question.id);
        const data = question.data;
        callbacks.current.onNeedsApproval?.({
          task: watch.task,
          sessionId,
          tool: data.baslik ?? data.arac ?? data.soru ?? "bir işlem",
        });
      } else if (!question && watch.sawRunning && !session.running) {
        watched.current.delete(sessionId);
      }
    }
    if (pending.current.length === 0) return;
    pending.current = pending.current.filter(({ sessionId, task }) => {
      // Oturum kurulamadı ya da kullanıcı kapattı: bekleyen görev çok sonra, oturum başka bir nedenle
      // hazır olursa geç gönderilmesin (U5-54).
      const session = sessions[sessionId];
      const durum = session?.status;
      if (durum === "crashed" || durum === "closed") return false;
      if (durum !== "ready") return true;
      const guard = guards.current.get(sessionId);
      if (guard !== "ok") {
        if (guard === undefined) {
          guards.current.set(sessionId, "checking");
          const sessionClient = session?.client;
          const check = sessionClient ? ensureUnattendedSafe(sessionClient) : Promise.reject(new Error("oturum istemcisi yok"));
          void check.then(
            () => { guards.current.set(sessionId, "ok"); setGuardTick((tick) => tick + 1); },
            (reason: unknown) => {
              guards.current.delete(sessionId);
              pending.current = pending.current.filter((entry) => entry.sessionId !== sessionId);
              callbacks.current.onBlocked?.(task, reason instanceof Error ? reason.message : String(reason));
            },
          );
        }
        return true;
      }
      if (!send(sessionId, task.gorev)) return true;
      guards.current.delete(sessionId);
      watched.current.set(sessionId, { task, notified: new Set(), sawRunning: false });
      onStarted?.(task);
      return false;
    });
  }, [onStarted, send, sessions, guardTick]);

  return {
    /** "Şimdi çalıştır": görevi takvimi beklemeden aynı yoldan başlatır. */
    async runNow(task: ScheduledTask) {
      const sessionId = await createRef.current({
        mode: "kod",
        root: task.kok,
        title: task.baslik,
      });
      pending.current = [...pending.current, { sessionId, task }];
    },
  };
}
