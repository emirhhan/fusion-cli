import {
  SCHEDULE_POLL_MS,
  isScheduleDelivery,
  isScheduleReceipt,
  type ScheduleDelivery,
  type ScheduleDeliveryClient,
  type ScheduleReceipt,
} from "../schedule/types";

interface MessageHost {
  addEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ): void;
  removeEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
interface Pending {
  delivery: ScheduleDelivery;
  nonce?: string;
  timer: ReturnType<typeof setTimeout>;
  resolve(value: ScheduleReceipt | null): void;
}
/** Bir iframe neslinin makbuzlarını doğrular; hesaplama başarısı kanıtlamaz. */
export class ScheduledDeliveryClient implements ScheduleDeliveryClient {
  private pending?: Pending;
  private closed = false;
  private readonly origin: string;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
  ) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }
  deliver(delivery: ScheduleDelivery): Promise<ScheduleReceipt | null> {
    if (this.closed || this.pending || !isScheduleDelivery(delivery))
      return Promise.resolve(null);
    return new Promise((resolve) => {
      const timer = setTimeout(() => this.finish(null), SCHEDULE_POLL_MS);
      this.pending = { delivery: { ...delivery }, timer, resolve };
      try {
        this.frame.postMessage(
          { type: "fusion-schedule-connect" },
          this.origin,
        );
      } catch {
        this.finish(null);
      }
    });
  }
  /** iframe yeniden yüklenince eski neslin yanıtları kullanılmaz. */
  reset() {
    this.finish(null);
  }
  close() {
    this.closed = true;
    this.finish(null);
    this.host.removeEventListener("message", this.receive);
  }
  private finish(receipt: ScheduleReceipt | null) {
    const pending = this.pending;
    this.pending = undefined;
    if (!pending) return;
    clearTimeout(pending.timer);
    pending.resolve(receipt);
  }
  private receive = (event: MessageEvent) => {
    const pending = this.pending;
    if (!pending || event.source !== this.frame || event.origin !== this.origin)
      return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object") return;
    if (data.type === "fusion-schedule-ready" && !pending.nonce) {
      if (
        typeof data.nonce !== "string" ||
        !data.nonce ||
        typeof data.threadId !== "string" ||
        !data.threadId ||
        data.root !== pending.delivery.root
      ) {
        this.finish(null);
        return;
      }
      pending.nonce = data.nonce;
      try {
        this.frame.postMessage(
          {
            type: "fusion-schedule-deliver",
            nonce: pending.nonce,
            threadId: data.threadId,
            root: pending.delivery.root,
            occurrenceId: pending.delivery.occurrence_id,
            prompt: pending.delivery.task,
          },
          this.origin,
        );
      } catch {
        this.finish(null);
      }
    } else if (
      data.type === "fusion-schedule-receipt" &&
      pending.nonce &&
      data.nonce === pending.nonce &&
      isScheduleReceipt(data, pending.delivery.occurrence_id)
    ) {
      this.finish({
        occurrenceId: data.occurrenceId,
        taskId: data.taskId,
        status: "queued",
      });
    }
  };
}
