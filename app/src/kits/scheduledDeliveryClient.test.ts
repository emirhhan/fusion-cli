import { createElement, useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScheduledDeliveryClient, type ScheduleApprovalListener } from "./scheduledDeliveryClient";
import { KitsScreen } from "./KitsScreen";
import {
  useScheduleRunner,
  SCHEDULE_POLL_MS,
} from "../schedule/useScheduleRunner";
import type { ScheduleDeliveryClient } from "../schedule/types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const delivery = {
  occurrence_id: "a".repeat(64),
  schedule_id: "schedule",
  due_at: 123,
  title: "Rapor",
  task: "Raporu çıkar",
  root: "/project",
  task_id: null,
};
const receipt = {
  type: "fusion-schedule-receipt",
  nonce: "connection-one",
  occurrenceId: delivery.occurrence_id,
  taskId: `schedule-${delivery.occurrence_id}`,
  status: "queued",
};
const ready = {
  type: "fusion-schedule-ready",
  nonce: "connection-one",
  threadId: "bound-thread",
  root: "/project",
};
function fixture(onApproval?: ScheduleApprovalListener) {
  let listener: (event: MessageEvent) => void = () => {};
  const frame = { postMessage: vi.fn() };
  const host = {
    addEventListener: (_type: string, handler: typeof listener) => {
      listener = handler;
    },
    removeEventListener: vi.fn(() => {
      listener = () => {};
    }),
  };
  const client = new ScheduledDeliveryClient(
    host,
    frame,
    "http://127.0.0.1:50001",
    onApproval,
  );
  return {
    client,
    frame,
    host,
    emit: (
      data: unknown,
      origin = "http://127.0.0.1:50001",
      source: unknown = frame,
    ) => listener({ data, origin, source } as MessageEvent),
  };
}
describe("ScheduledDeliveryClient", () => {
  it("makbuz exact iframe/origin/nonce/occurrence/task/status gerektirir", async () => {
    const f = fixture();
    const promise = f.client.deliver(delivery);
    f.emit(ready, "http://evil.example");
    f.emit(ready, undefined, {});
    expect(f.frame.postMessage).toHaveBeenCalledTimes(1);
    f.emit(ready);
    expect(f.frame.postMessage).toHaveBeenLastCalledWith(
      {
        type: "fusion-schedule-deliver",
        nonce: ready.nonce,
        threadId: ready.threadId,
        root: delivery.root,
        occurrenceId: delivery.occurrence_id,
        prompt: delivery.task,
        unattended: true,
        onApproval: "pause",
      },
      "http://127.0.0.1:50001",
    );
    let settled = false;
    void promise.then(() => {
      settled = true;
    });
    for (const change of [
      { nonce: "old" },
      { occurrenceId: "b".repeat(64) },
      { taskId: "other" },
      { status: "completed" },
    ])
      f.emit({ ...receipt, ...change });
    f.emit(receipt, "null");
    f.emit(receipt, undefined, {});
    await Promise.resolve();
    expect(settled).toBe(false);
    f.emit(receipt);
    expect(await promise).toEqual({
      occurrenceId: delivery.occurrence_id,
      taskId: receipt.taskId,
      status: "queued",
    });
    f.client.close();
  });
  it("root uyuşmazlığı, eksik thread ve RAM boolean makbuz olmaz", async () => {
    for (const change of [{ root: "/other" }, { threadId: "" }]) {
      const f = fixture();
      const promise = f.client.deliver(delivery);
      f.emit({ ...ready, ...change });
      expect(await promise).toBeNull();
      expect(f.frame.postMessage).toHaveBeenCalledOnce();
      f.client.close();
    }
    const f = fixture();
    const promise = f.client.deliver(delivery);
    f.emit(true);
    f.client.close();
    expect(await promise).toBeNull();
  });
  it("tek uçuş; mevcut yoklama aralığında timeout ve aynı occurrence yeniden denenir", async () => {
    vi.useFakeTimers();
    const f = fixture();
    const first = f.client.deliver(delivery);
    expect(await f.client.deliver(delivery)).toBeNull();
    await vi.advanceTimersByTimeAsync(SCHEDULE_POLL_MS);
    expect(await first).toBeNull();
    const second = f.client.deliver(delivery);
    f.emit({ ...ready, nonce: "connection-two" });
    f.emit(receipt);
    f.emit({ ...receipt, nonce: "connection-two" });
    expect(await second).toMatchObject({ taskId: receipt.taskId });
    f.client.close();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("reload/close eski makbuzu düşürür ve beklemeyi temizler", async () => {
    const f = fixture();
    const first = f.client.deliver(delivery);
    f.emit(ready);
    f.client.reset();
    expect(await first).toBeNull();
    const second = f.client.deliver(delivery);
    f.emit({ ...ready, nonce: "new" });
    f.emit(receipt);
    f.client.close();
    expect(await second).toBeNull();
    expect(await f.client.deliver(delivery)).toBeNull();
    expect(f.host.removeEventListener).toHaveBeenCalledOnce();
  });
});
describe("Kits kuyruğundaki görev onay isterse (U5-57)", () => {
  const approval = {
    type: "fusion-schedule-approval",
    occurrenceId: delivery.occurrence_id,
    taskId: `schedule-${delivery.occurrence_id}`,
    tool: "run_shell",
  };
  it("teslim mesajı gözetimsiz olduğunu ve onayda askıya alınacağını bildirir", () => {
    const f = fixture();
    void f.client.deliver(delivery);
    f.emit(ready);
    const mesaj = f.frame.postMessage.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(mesaj).toMatchObject({ unattended: true, onApproval: "pause" });
    f.client.close();
  });

  it("Kits'ten gelen geçerli onay bildirimi teslim başlığıyla dinleyiciye iletilir", async () => {
    const onApproval = vi.fn();
    const f = fixture(onApproval);
    const promise = f.client.deliver(delivery);
    f.emit(ready);
    f.emit(receipt);
    await promise;

    f.emit(approval);

    expect(onApproval).toHaveBeenCalledWith({
      occurrenceId: delivery.occurrence_id,
      taskId: approval.taskId,
      title: delivery.title,
      tool: "run_shell",
    });
    f.client.close();
  });

  it("aynı vade ve araç için tekrarlanan bildirim bir kez gösterilir", () => {
    const onApproval = vi.fn();
    const f = fixture(onApproval);
    f.emit(approval);
    f.emit(approval);
    f.emit({ ...approval, tool: "write_file" });
    expect(onApproval).toHaveBeenCalledTimes(2);
    f.client.close();
  });

  it("yabancı köken, yabancı pencere, bozuk kimlik ve boş araç adı yok sayılır", () => {
    const onApproval = vi.fn();
    const f = fixture(onApproval);
    f.emit(approval, "http://evil.example");
    f.emit(approval, undefined, {});
    f.emit({ ...approval, occurrenceId: "zzz" });
    f.emit({ ...approval, taskId: "schedule-baska" });
    f.emit({ ...approval, tool: "  " });
    f.emit({ ...approval, tool: 5 });
    expect(onApproval).not.toHaveBeenCalled();
    f.client.close();
  });

  it("uzun araç adı kısaltılır; kapatılmış istemci bildirim iletmez", () => {
    const onApproval = vi.fn();
    const f = fixture(onApproval);
    f.emit({ ...approval, tool: "x".repeat(500) });
    expect(onApproval.mock.calls[0][0].tool).toHaveLength(200);
    f.client.close();
    f.emit({ ...approval, tool: "baska" });
    expect(onApproval).toHaveBeenCalledTimes(1);
  });

  it("dinleyici verilmemişse (eski kurulum) bildirim sessizce düşer", () => {
    const f = fixture();
    expect(() => f.emit(approval)).not.toThrow();
    f.client.close();
  });
});
it("mounted KitsScreen + runner yalnız actual iframe makbuzunu çekirdeğe ack verir", async () => {
  vi.useFakeTimers();
  const request = vi.fn(async (name: string) =>
    name === "zamanlama.teslim_bekleyenler"
      ? { ok: true, teslimler: [delivery] }
      : { ok: true },
  );
  const create = vi.fn(async () => "native");
  const send = vi.fn(() => true);
  const core = { request };
  const start = async () => ({ url: "http://127.0.0.1:50001" });
  function Harness() {
    const [client, setClient] = useState<ScheduleDeliveryClient | null>(null);
    useScheduleRunner({
      client: core,
      deliveryClient: client,
      create,
      send,
      sessions: {},
    });
    return createElement(KitsScreen, { start, onDeliveryClient: setClient });
  }
  render(createElement(Harness));
  await act(async () => {
    await Promise.resolve();
  });
  const frame = screen.getByTitle("Fusion Kits") as HTMLIFrameElement;
  const post = vi.spyOn(frame.contentWindow!, "postMessage");
  fireEvent.load(frame);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(SCHEDULE_POLL_MS);
  });
  expect(post).toHaveBeenCalledWith(
    { type: "fusion-schedule-connect" },
    "http://127.0.0.1:50001",
  );
  await act(async () => {
    window.dispatchEvent(
      new MessageEvent("message", {
        data: ready,
        origin: "http://127.0.0.1:50001",
        source: frame.contentWindow,
      }),
    );
    window.dispatchEvent(
      new MessageEvent("message", {
        data: receipt,
        origin: "http://127.0.0.1:50001",
        source: frame.contentWindow,
      }),
    );
  });
  expect(request).toHaveBeenCalledWith("zamanlama.teslim_onayla", {
    occurrence_id: delivery.occurrence_id,
    task_id: receipt.taskId,
  });
  expect(create).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
});
