import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useSessionCron } from "./useSessionCron";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function makeClient(gorevler: unknown[]) {
  const request = vi.fn(async () => ({ ok: true, gorevler }));
  return { request };
}

// P-038: vadesi gelen görev boştaki sohbete normal tur olarak gönderilir.
it("boştaki sohbette vadesi gelen görevi tur olarak gönderir", async () => {
  const client = makeClient([{ id: "ab12", gorev: "testleri koştur" }]);
  const send = vi.fn(() => true);
  const onFired = vi.fn();
  renderHook(() => useSessionCron({ session: { id: "s1", status: "ready", running: false, client }, send, onFired, pollMs: 1000 }));

  await vi.advanceTimersByTimeAsync(1000);

  expect(client.request).toHaveBeenCalledWith("cron.vadesi_gelenler", {});
  expect(send).toHaveBeenCalledWith("s1", "testleri koştur");
  expect(onFired).toHaveBeenCalledWith({ id: "ab12", gorev: "testleri koştur" });
});

it("tur sürerken ya da soru beklerken yoklamaz", async () => {
  const client = makeClient([{ id: "x", gorev: "a" }]);
  const send = vi.fn(() => true);
  const { rerender } = renderHook(
    (props: { running: boolean; question: unknown }) =>
      useSessionCron({ session: { id: "s1", status: "ready", running: props.running, question: props.question, client }, send, pollMs: 1000 }),
    { initialProps: { running: true, question: null } },
  );
  await vi.advanceTimersByTimeAsync(1000);
  rerender({ running: false, question: { id: "q" } });
  await vi.advanceTimersByTimeAsync(1000);

  expect(client.request).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
});

it("hazır olmayan sohbette aralık kurulmaz, bozuk yanıt gönderim yapmaz", async () => {
  const client = makeClient([{ id: "x" }]);
  const send = vi.fn(() => true);
  renderHook(() => useSessionCron({ session: { id: "s1", status: "starting", running: false, client }, send, pollMs: 1000 }));
  await vi.advanceTimersByTimeAsync(1000);
  expect(client.request).not.toHaveBeenCalled();

  renderHook(() => useSessionCron({ session: { id: "s2", status: "ready", running: false, client }, send, pollMs: 1000 }));
  await vi.advanceTimersByTimeAsync(1000);
  expect(client.request).toHaveBeenCalledTimes(1);
  expect(send).not.toHaveBeenCalled();
});
