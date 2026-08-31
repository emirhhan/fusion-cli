import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke, listen } = vi.hoisted(() => ({ invoke: vi.fn(), listen: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen }));

import { createTerminalRuntime } from "./terminalBridge";

beforeEach(() => {
  invoke.mockReset();
  listen.mockReset();
});

describe("terminalBridge", () => {
  it("terminal_ac sırasında senkron gelen ilk çıktıyı listener-before-open buffer'ından teslim eder", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockImplementation(async (command: string) => {
      if (command === "terminal_ac") {
        handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-fast", data: [36, 32] } });
        return { terminalId: "terminal-fast", cwd: "/repo", cols: 80, rows: 24, pid: 42 };
      }
    });

    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const output = vi.fn();
    session.onOutput(output);

    expect(output).toHaveBeenCalledWith(new Uint8Array([36, 32]));
    expect(listen.mock.invocationCallOrder[1]).toBeLessThan(invoke.mock.invocationCallOrder[0]);
  });

  it("terminal_ac sırasında senkron gelen hızlı kapanmayı buffer'lar ve close'u idempotent yapar", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockImplementation(async (command: string) => {
      if (command === "terminal_ac") {
        handlers.get("terminal://kapandi")?.({ payload: { terminalId: "terminal-fast", reason: "shell exited" } });
        return { terminalId: "terminal-fast", cwd: "/repo", cols: 80, rows: 24, pid: 42 };
      }
    });

    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const closed = vi.fn();
    session.onClosed(closed);
    await session.close();

    expect(closed).toHaveBeenCalledWith("shell exited");
    expect(invoke.mock.calls).toEqual([["terminal_ac", { cwd: "/repo", cols: 80, rows: 24 }]]);
  });

  it("Tauri terminal komutlarını kesin ad ve payload ile çağırır", async () => {
    invoke.mockResolvedValueOnce({ terminalId: "terminal-7", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const runtime = createTerminalRuntime();

    await expect(runtime.open("/repo", 80, 24)).resolves.toEqual({
      terminalId: "terminal-7", cwd: "/repo", cols: 80, rows: 24, pid: 42,
    });
    await runtime.write("terminal-7", new Uint8Array([3, 10]));
    await runtime.resize("terminal-7", 120, 36);
    await runtime.close("terminal-7");

    expect(invoke.mock.calls).toEqual([
      ["terminal_ac", { cwd: "/repo", cols: 80, rows: 24 }],
      ["terminal_yaz", { terminalId: "terminal-7", data: [3, 10] }],
      ["terminal_boyutla", { terminalId: "terminal-7", cols: 120, rows: 36 }],
      ["terminal_kapat", { terminalId: "terminal-7" }],
    ]);
  });

  it("çıktı ve kapanma olaylarını süzer ve dönen işlevle dinleyiciyi kaldırır", async () => {
    const outputUnlisten = vi.fn();
    const closedUnlisten = vi.fn();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      if (name === "terminal://cikti") {
        handler({ payload: { terminalId: "terminal-2", data: [226, 130] } });
        return outputUnlisten;
      }
      handler({ payload: { terminalId: "terminal-2", reason: "çıktı" } });
      return closedUnlisten;
    });
    const runtime = createTerminalRuntime();
    const onOutput = vi.fn();
    const onClosed = vi.fn();

    const stopOutput = await runtime.onOutput("terminal-2", onOutput);
    const stopClosed = await runtime.onClosed("terminal-2", onClosed);
    stopOutput();
    stopClosed();

    expect(listen.mock.calls.map(([name]) => name)).toEqual(["terminal://cikti", "terminal://kapandi"]);
    expect(onOutput).toHaveBeenCalledWith(new Uint8Array([226, 130]));
    expect(onClosed).toHaveBeenCalledWith("çıktı");
    expect(outputUnlisten).toHaveBeenCalledOnce();
    expect(closedUnlisten).toHaveBeenCalledOnce();
  });
});
