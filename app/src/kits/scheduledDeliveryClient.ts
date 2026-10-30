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
/** Kits'teki zamanlanmış görev onay isteyen bir araca takıldı (kullanıcı yokken ilerlemez). */
export interface ScheduleApprovalRequest {
  occurrenceId: string;
  taskId: string;
  title: string;
  tool: string;
}
export type ScheduleApprovalListener = (request: ScheduleApprovalRequest) => void;

const TOOL_LIMIT = 200;
/** Başlık ve tekrar bastırma tabloları sınırlıdır; uzun oturumda büyümez. */
const REMEMBER_LIMIT = 100;
const FALLBACK_TITLE = "Zamanlanmış görev";

/** Bir iframe neslinin makbuzlarını doğrular; hesaplama başarısı kanıtlamaz. */
export class ScheduledDeliveryClient implements ScheduleDeliveryClient {
  private pending?: Pending;
  private closed = false;
  private readonly origin: string;
  private readonly titles = new Map<string, string>();
  private readonly announced = new Set<string>();
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly onApproval?: ScheduleApprovalListener,
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
  /**
   * Kits'in "bu zamanlanmış görev onay bekliyor" bildirimi. Yalnız bilgidir: Fusion hiçbir
   * şeyi onaylamaz/reddetmez, sadece kullanıcıya haber verir (U5-57). Bekleyen teslim
   * gerekmez: makbuzdan çok sonra gelebilir; kimlik biçimi ve `schedule-<vade>` bağı doğrulanır.
   */
  private approval(data: Record<string, unknown>) {
    const { occurrenceId, taskId, tool } = data;
    if (
      !this.onApproval ||
      typeof occurrenceId !== "string" ||
      !/^[a-f0-9]{64}$/.test(occurrenceId) ||
      taskId !== `schedule-${occurrenceId}` ||
      typeof tool !== "string" ||
      !tool.trim()
    )
      return;
    const name = tool.trim().slice(0, TOOL_LIMIT);
    const key = `${occurrenceId}|${name}`;
    if (this.announced.has(key)) return;
    this.announced.add(key);
    trimOldest(this.announced);
    this.onApproval({
      occurrenceId,
      taskId,
      title: this.titles.get(occurrenceId) ?? FALLBACK_TITLE,
      tool: name,
    });
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin)
      return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object") return;
    if (data.type === "fusion-schedule-approval") {
      this.approval(data);
      return;
    }
    const pending = this.pending;
    if (!pending) return;
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
            // Gözetimsiz çalışma: onay isteyen araçta Kits görevi kullanıcı yanıtlayana kadar
            // askıda tutmalı ve `fusion-schedule-approval` ile haber vermelidir. Eski Kits
            // bilinmeyen alanları yok sayar.
            unattended: true,
            onApproval: "pause",
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
      this.titles.set(pending.delivery.occurrence_id, pending.delivery.title);
      trimOldest(this.titles);
      this.finish({
        occurrenceId: data.occurrenceId,
        taskId: data.taskId,
        status: "queued",
      });
    }
  };
}

/** Sınırı aşan en eski girdiyi at (Map ve Set ekleme sırasını korur). */
function trimOldest(store: Map<string, string> | Set<string>) {
  while (store.size > REMEMBER_LIMIT) {
    const oldest = store.keys().next();
    if (oldest.done) return;
    store.delete(oldest.value);
  }
}
