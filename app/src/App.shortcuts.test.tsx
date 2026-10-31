import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionUygulama } from "./App";
import type { SessionTransport } from "./sessions/types";

const nativeDrops = vi.hoisted(() => {
  const state: { handler: ((paths: string[]) => void) | null } = { handler: null };
  const unlisten = vi.fn();
  const listen = vi.fn(async (handler: (paths: string[]) => void) => {
    state.handler = handler;
    return unlisten;
  });
  return { listen, state, unlisten };
});
const nativeInvoke = vi.hoisted(() => vi.fn(async (command: string) => {
  if (command.startsWith("izin_")) return { state: "granted", supported: true };
  if (command === "terminal_ac_kanal") return { terminalId: "terminal-1", cwd: "/proje", cols: 80, rows: 24, pid: 77 };
  return undefined;
}));

vi.mock("./platform/drop", () => ({ listenForFileDrops: nativeDrops.listen }));
vi.mock("@tauri-apps/api/core", () => ({
  invoke: nativeInvoke,
  Channel: class { onmessage: (message: unknown) => void = () => undefined; },
}));
vi.mock("@tauri-apps/api/path", () => ({ desktopDir: vi.fn(async () => "/Users/test/Desktop") }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => vi.fn()) }));
vi.mock("./processes/XtermSession", () => ({
  XtermSession: ({ session }: { session: { snapshot: { terminalId: string } } }) => (
    <div>PTY {session.snapshot.terminalId}</div>
  ),
  // Gerçek ölçüm xterm'i ve bir tarayıcıyı gerektirir; jsdom'da varsayılana düşer.
  measureTerminalSize: () => ({ cols: 0, rows: 0 }),
}));

function composerTransport(responses: Record<string, Record<string, unknown>> = {}) {
  let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
  const requests: Array<{ ad: string; id: string; veri: Record<string, unknown> }> = [];
  const transport: SessionTransport = {
    create: vi.fn(async (id) => ({
      oturum_id: id,
      kok: "/proje",
      pid: 41,
      durum: "calisiyor",
      kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      const request = JSON.parse(line) as { ad: string; id: string; veri: Record<string, unknown> };
      requests.push(request);
      queueMicrotask(() => lineHandler?.({
        oturum_id: id,
        satir: JSON.stringify({
          tip: "sonuc",
          id: request.id,
          veri: responses[request.ad] ?? { ok: true },
        }),
      }));
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
    onClosed: vi.fn(async () => () => undefined),
  };
  return { requests, transport };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const ctrl = (key: string, code: string, extra: KeyboardEventInit = {}) =>
  fireEvent.keyDown(window, { key, code, ctrlKey: true, ...extra });

// Global kısayollar ve komut paleti uçtan uca (P-046). jsdom macOS değildir: mod = Ctrl.
describe("uygulama kısayolları", () => {
  it("Ctrl+K paleti açar; paletten Ayarlar › Kısayollar açılır; Esc kapatır", async () => {
    const fake = composerTransport({ "ayar.arayuz": { ok: true, degerler: {} } });
    render(<SessionUygulama transport={fake.transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    ctrl("k", "KeyK");
    const input = await screen.findByRole("combobox", { name: /ara/ });
    fireEvent.change(input, { target: { value: "?kısayol" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByRole("heading", { name: "Kısayollar" })).toBeTruthy();
    await waitFor(() => expect(fake.requests.some((request) => request.ad === "kisayol.liste")).toBe(true));
    ctrl("k", "KeyK");
    fireEvent.keyDown(await screen.findByRole("combobox", { name: /Komut, sohbet/ }), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("combobox", { name: /Komut, sohbet/ })).toBeNull());
  });

  it("Ctrl+, ayarları, Ctrl+B kenar çubuğunu, Ctrl+P dosya aramasını açar", async () => {
    const fake = composerTransport({
      "ayar.arayuz": { ok: true, degerler: {} },
      "proje.dosya_ara": { ok: true, sonuclar: [{ yol: "src/app.py", vurgu: [] }] },
    });
    render(<SessionUygulama transport={fake.transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    const sidebar = screen.getByRole("navigation", { name: "Fusion" });
    const before = sidebar.getAttribute("data-collapsed");
    ctrl("b", "KeyB");
    await waitFor(() => expect(screen.getByRole("navigation", { name: "Fusion" }).getAttribute("data-collapsed")).not.toBe(before));
    ctrl("p", "KeyP");
    const input = await screen.findByRole("combobox", { name: /Komut, sohbet/ });
    expect((input as HTMLInputElement).value).toBe("@");
    fireEvent.change(input, { target: { value: "@app" } });
    expect(await screen.findByText("app.py")).toBeTruthy();
    expect(fake.requests.find((request) => request.ad === "proje.dosya_ara")?.veri).toEqual({ sorgu: "app", limit: 20 });
    fireEvent.keyDown(input, { key: "Escape" });
    ctrl(",", "Comma");
    expect(await screen.findByRole("dialog", { name: "Ayarlar" })).toBeTruthy();
  });

  it("/keybindings masaüstünde Ayarlar › Kısayollar'ı açar, çekirdeğe komut gitmez", async () => {
    const fake = composerTransport({ "ayar.arayuz": { ok: true, degerler: {} } });
    render(<SessionUygulama transport={fake.transport} />);
    const box = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(box, { target: { value: "/keybindings" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(await screen.findByRole("heading", { name: "Kısayollar" })).toBeTruthy();
    expect(fake.requests.some((request) => request.ad === "komut.calistir")).toBe(false);
  });
});
