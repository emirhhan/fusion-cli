import { useEffect, useRef } from "react";
import {
  SCHEDULE_POLL_MS,
  isScheduleDelivery,
  isScheduleReceipt,
  type ScheduleClient,
  type ScheduledTask,
  type ScheduleDeliveryClient,
} from "./types";
export { SCHEDULE_POLL_MS } from "./types";

interface RunnerSession {
  status: string;
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
}

interface Pending {
  sessionId: string;
  task: ScheduledTask;
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
      await deliverPending(client, deliveryClient, inFlight, () => active);
    } catch {
      // Makbuz veya ack yoksa çekirdeğin kalıcı teslim kaydı sonraki yoklamada kalır.
    } finally {
      polling.current = false;
    }
  };
  void poll();
  const timer = window.setInterval(() => void poll(), SCHEDULE_POLL_MS);
  return () => {
    active = false;
    window.clearInterval(timer);
  };
}

/** Otomatik vadeler kalıcı Kits kuyruğuna teslim edilir; manuel yol sohbet açar. */
export function useScheduleRunner({
  client,
  create,
  send,
  sessions,
  onStarted,
  deliveryClient,
}: ScheduleRunnerInput) {
  const pending = useRef<Pending[]>([]);
  const createRef = useRef(create);
  createRef.current = create;

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
      const sessionId = await createRef.current({
        mode: "kod",
        root: task.kok,
        title: task.baslik,
      });
      pending.current = [...pending.current, { sessionId, task }];
    },
  };
}
