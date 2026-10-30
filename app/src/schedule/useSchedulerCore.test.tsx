import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSchedulerCore } from "./useSchedulerCore";
import type { SchedulerCore } from "./schedulerCore";
import type { SessionTransport } from "../sessions/types";

const transport = {} as SessionTransport;

function fakeCore(): SchedulerCore & { close: ReturnType<typeof vi.fn> } {
  return { client: { request: vi.fn(async () => ({ ok: true })) }, close: vi.fn(async () => undefined) };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const settle = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });

describe("useSchedulerCore", () => {
  it("hazır sohbet varken çekirdek açmaz", async () => {
    const open = vi.fn();
    const { result } = renderHook(() => useSchedulerCore({ transport, needed: false, open }));
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });

    expect(open).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });

  it("sohbet gelene kadar bekler (açılışta sekme geri yüklenirken ikinci süreç açılmaz)", async () => {
    const open = vi.fn(async () => fakeCore());
    const { rerender } = renderHook(({ needed }) => useSchedulerCore({ transport, needed, graceMs: 20_000, open }), {
      initialProps: { needed: true },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(19_000); });
    rerender({ needed: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(open).not.toHaveBeenCalled();
  });

  it("sohbet yokken bekleme süresinden sonra çekirdeği açar ve istemciyi verir", async () => {
    const core = fakeCore();
    const open = vi.fn(async () => core);
    const { result } = renderHook(() => useSchedulerCore({ transport, needed: true, graceMs: 20_000, open }));

    expect(result.current).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });

    expect(open).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(core.client);
  });

  it("sohbet açılınca görünmez çekirdeği kapatır", async () => {
    const core = fakeCore();
    const { result, rerender } = renderHook(({ needed }) => useSchedulerCore({ transport, needed, graceMs: 10, open: async () => core }), {
      initialProps: { needed: true },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(result.current).toBe(core.client);

    rerender({ needed: false });

    expect(core.close).toHaveBeenCalledTimes(1);
    expect(result.current).toBeNull();
  });

  it("açılış sürerken sohbet gelirse gelen çekirdek hemen kapatılır, istemci verilmez", async () => {
    const core = fakeCore();
    let finish: (value: SchedulerCore) => void = () => undefined;
    const open = vi.fn(() => new Promise<SchedulerCore>((resolve) => { finish = resolve; }));
    const { result, rerender } = renderHook(({ needed }) => useSchedulerCore({ transport, needed, graceMs: 10, open }), {
      initialProps: { needed: true },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    rerender({ needed: false });
    finish(core);
    await settle();

    expect(core.close).toHaveBeenCalledTimes(1);
    expect(result.current).toBeNull();
  });

  it("açılış başarısızsa artan beklemeyle yeniden dener", async () => {
    const core = fakeCore();
    const open = vi.fn<() => Promise<SchedulerCore>>()
      .mockRejectedValueOnce(new Error("çalışma zamanı hazır değil"))
      .mockResolvedValue(core);
    const { result } = renderHook(() => useSchedulerCore({ transport, needed: true, graceMs: 10, retryMs: 1_000, open }));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(result.current).toBeNull();

    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

    expect(open).toHaveBeenCalledTimes(2);
    expect(result.current).toBe(core.client);
  });

  it("çekirdek çökerse istemci düşer ve yeniden açılır", async () => {
    const [first, second] = [fakeCore(), fakeCore()];
    let onClosed: (reason: string) => void = () => undefined;
    const open = vi.fn<(t: SessionTransport, c: (reason: string) => void) => Promise<SchedulerCore>>()
      .mockImplementationOnce(async (_t, closed) => { onClosed = closed; return first; })
      .mockResolvedValue(second);
    const { result } = renderHook(() => useSchedulerCore({ transport, needed: true, graceMs: 10, retryMs: 1_000, open }));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(result.current).toBe(first.client);

    act(() => onClosed("süreç kapandı"));
    expect(result.current).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

    expect(result.current).toBe(second.client);
  });

  it("bileşen kalkınca çekirdeği kapatır", async () => {
    const core = fakeCore();
    const { unmount } = renderHook(() => useSchedulerCore({ transport, needed: true, graceMs: 10, open: async () => core }));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });

    unmount();

    expect(core.close).toHaveBeenCalledTimes(1);
  });
});
