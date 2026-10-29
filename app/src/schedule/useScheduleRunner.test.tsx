import { renderHook, cleanup, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScheduleRunner } from "./useScheduleRunner";
import type { ScheduleDelivery, ScheduleReceipt } from "./types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function delivery(letter: string): ScheduleDelivery {
  return {
    occurrence_id: letter.repeat(64),
    schedule_id: `schedule-${letter}`,
    due_at: 100,
    title: `Görev ${letter}`,
    task: "incele",
    root: "/proje",
    task_id: null,
  };
}
function queued(item: ScheduleDelivery): ScheduleReceipt {
  return { occurrenceId: item.occurrence_id, taskId: `schedule-${item.occurrence_id}`, status: "queued" };
}
function core(items: ScheduleDelivery[], failAck: (id: string) => boolean = () => false) {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "zamanlama.teslim_bekleyenler") return { ok: true, teslimler: items };
      if (name === "zamanlama.teslim_onayla" && failAck(String(data.occurrence_id))) {
        throw new Error("ack yazılamadı");
      }
      return { ok: true };
    }),
  };
}
async function runOnePoll(client: ReturnType<typeof core>, deliver: (item: ScheduleDelivery) => Promise<ScheduleReceipt | null>) {
  renderHook(() =>
    useScheduleRunner({
      client,
      deliveryClient: { deliver },
      create: async () => "x",
      send: () => true,
      sessions: {},
    }),
  );
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}
const acked = (client: ReturnType<typeof core>) =>
  client.request.mock.calls
    .filter(([name]) => name === "zamanlama.teslim_onayla")
    .map(([, data]) => data.occurrence_id);

describe("useScheduleRunner teslim döngüsü", () => {
  it("ilk teslim istisna fırlatsa da sonraki teslim aynı turda ilerler", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second]);
    const deliver = vi.fn(async (item: ScheduleDelivery) => {
      if (item === first) throw new Error("Kits yanıt vermedi");
      return queued(item);
    });
    await runOnePoll(client, deliver);
    expect(deliver).toHaveBeenCalledTimes(2);
    expect(acked(client)).toEqual([second.occurrence_id]);
  });

  it("ack yazımı başarısız olsa da sonraki teslim ilerler; ack'siz kayıt kuyrukta kalır", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second], (id) => id === first.occurrence_id);
    await runOnePoll(client, async (item) => queued(item));
    expect(acked(client)).toEqual([first.occurrence_id, second.occurrence_id]);
  });

  it("makbuz dönmeyen teslim ack almaz, sonrakini engellemez", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second]);
    await runOnePoll(client, async (item) => (item === first ? null : queued(item)));
    expect(acked(client)).toEqual([second.occurrence_id]);
  });
});
