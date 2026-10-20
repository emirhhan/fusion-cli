import { afterEach, expect, it, vi } from "vitest";
import { createScreenStream } from "../../../src/fusion_cli/remote/pwa/screen-stream.js";
afterEach(() => vi.useRealTimers());
it("telefondaki açık onayı ve hatırlama tercihini sunucuya iletir", async () => {
  const rpc = vi.fn(async (method) => method === "screen.status" ? { ok: true, data: { state: "none" } } : method === "screen.request" ? { ok: true } : { ok: false, error: "ekran_onay_yok" });
  const states = [];
  const stream = createScreenStream({ rpc, onFrame: vi.fn(), onState: (state) => states.push(state.state) });
  await stream.start({ remember: true, confirmed: true });
  await vi.waitFor(() => expect(states).toContain("ended"));
  expect(rpc).toHaveBeenCalledWith("screen.request", { remember: true, confirmed: true });
  expect(rpc.mock.calls.filter(([method]) => method === "screen.request")).toHaveLength(1);
});
it("etkin oturum sona erdiğinde kendiliğinden izin istemez", async () => {
  vi.useFakeTimers();
  let live = true;
  const rpc = vi.fn(async (method) => method === "screen.status" ? { ok: true, data: { state: live ? "active" : "none" } } : live ? { ok: true, data: { jpegBase64: "YWJj" } } : { ok: false, error: "ekran_onay_yok" });
  const onState = vi.fn();
  const stream = createScreenStream({ rpc, onFrame: vi.fn(), onState });
  await stream.start({ request: false });
  await vi.advanceTimersByTimeAsync(0);
  live = false;
  await vi.advanceTimersByTimeAsync(600);
  expect(onState).toHaveBeenCalledWith({ state: "ended" });
  expect(rpc.mock.calls.some(([method]) => method === "screen.request")).toBe(false);
  stream.detach();
});
it("görünmezken kare istemez; ayırma sunucu iznini kaldırmaz", async () => {
  vi.useFakeTimers();
  const rpc = vi.fn(async () => ({ ok: true, data: { state: "active" } }));
  const stream = createScreenStream({ rpc, onFrame: vi.fn(), onState: vi.fn() });
  stream.setVisible(false); await stream.start({ request: false });
  await vi.advanceTimersByTimeAsync(3000);
  expect(rpc.mock.calls.some(([method]) => method === "screen.frame")).toBe(false);
  stream.setVisible(true); await vi.advanceTimersByTimeAsync(0);
  expect(rpc.mock.calls.some(([method]) => method === "screen.frame")).toBe(true);
  stream.detach();
  expect(rpc.mock.calls.some(([method]) => method === "screen.stop")).toBe(false);
});
it("durdurma başarısızsa iznin kalktığını söylemez", async () => {
  const onState = vi.fn();
  const stream = createScreenStream({ rpc: vi.fn(async () => ({ ok: false })), onFrame: vi.fn(), onState });
  await stream.stop();
  expect(onState).toHaveBeenCalledWith(expect.objectContaining({ state: "error" }));
  expect(onState).not.toHaveBeenCalledWith({ state: "stopped" });
});

it("bekleyen izin yalnız açık telefon onayıyla yeniden istenir", async () => {
  const rpc = vi.fn(async (method) => method === "screen.status" ? { ok: true, data: { state: "pending" } } : { ok: true });
  const stream = createScreenStream({ rpc, onFrame: vi.fn(), onState: vi.fn(), sleep: () => new Promise(() => {}) });
  await stream.start({ request: true, remember: true, confirmed: true });
  expect(rpc).toHaveBeenCalledWith("screen.request", { remember: true, confirmed: true });
  stream.detach();
});
