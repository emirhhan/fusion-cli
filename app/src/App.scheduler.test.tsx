import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionUygulama } from "./App";
import type { SessionLineEvent, SessionTransport } from "./sessions/types";

vi.mock("./platform/drop", () => ({ listenForFileDrops: vi.fn(async () => vi.fn()) }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => undefined) }));
vi.mock("@tauri-apps/api/path", () => ({ desktopDir: vi.fn(async () => "/Users/test/Desktop") }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => vi.fn()) }));
vi.mock("./processes/XtermSession", () => ({ XtermSession: () => null, measureTerminalSize: () => ({ cols: 0, rows: 0 }) }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.useRealTimers();
});

/** Sohbet oturumları açılamaz (çalışma zamanı hazır değil); yalnız zamanlayıcı çekirdeği açılır. */
function transportWithoutChats() {
  const handlers: ((event: SessionLineEvent) => void)[] = [];
  const requests: { oturum: string; ad: string; veri: Record<string, unknown> }[] = [];
  const transport: SessionTransport = {
    create: vi.fn(async (id) => {
      if (id !== "zamanlayici") throw new Error("sohbet çekirdeği açılamadı");
      return { oturum_id: id, kok: "/home", pid: 7, durum: "calisiyor" as const, kapanis_nedeni: null };
    }),
    send: vi.fn(async (id, line) => {
      const istek = JSON.parse(line) as { id: string; ad: string; veri: Record<string, unknown> };
      requests.push({ oturum: id, ad: istek.ad, veri: istek.veri });
      const veri = istek.ad === "zamanlama.teslim_bekleyenler" ? { ok: true, teslimler: [] } : { ok: true, sahip: true };
      queueMicrotask(() => handlers.forEach((handler) => handler({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: istek.id, veri }) })));
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => { handlers.push(handler); return () => undefined; }),
    onClosed: vi.fn(async () => () => undefined),
  };
  return { transport, requests };
}

describe("sohbetsiz zamanlayıcı (U5-52)", () => {
  it("hiç sohbet açılamadıysa görünmez çekirdek açılır ve vadesi gelenler alınır", async () => {
    vi.useFakeTimers();
    const { transport, requests } = transportWithoutChats();
    render(<SessionUygulama transport={transport} />);

    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(requests.filter((istek) => istek.oturum === "zamanlayici")).toEqual([]);
    expect(transport.create).not.toHaveBeenCalledWith("zamanlayici", undefined);

    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });

    expect(transport.create).toHaveBeenCalledWith("zamanlayici", undefined);
    const adlar = requests.filter((istek) => istek.oturum === "zamanlayici").map((istek) => istek.ad);
    expect(adlar).toEqual(expect.arrayContaining(["zamanlama.sahiplik", "zamanlama.vadesi_gelenler", "zamanlama.teslim_bekleyenler"]));
    // Görünmez oturum konuşma kurmaz: oturum.baslat (sohbet kimliği bağlama) gönderilmez.
    expect(requests.some((istek) => istek.oturum === "zamanlayici" && istek.ad === "oturum.baslat")).toBe(false);
  });
});
