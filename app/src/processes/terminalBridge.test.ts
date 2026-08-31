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
