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
  it("overflow'da split UTF-8 unit'i retention'a almaz; live akışı eksiksiz sürdürür", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const live: Uint8Array[] = [];
    session.onOutput((data) => live.push(data));
    const emit = (data: number[]) => handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-1", data } });
    emit([36, 32]);
    emit(new Array<number>(256 * 1024 - 2).fill(97));
    emit([226, 130]);
    emit([172]);
    const replay: Uint8Array[] = [];
    session.onOutput((data) => replay.push(data));

    expect(Array.from(replay[0])).toEqual([36, 32]);
    expect(replay.reduce((total, data) => total + data.byteLength, 0)).toBe(256 * 1024);
    expect(Array.from(replay.at(-1)!.slice(-3))).toEqual([97, 97, 97]);
    expect(Array.from(live.at(-2)!)).toEqual([226, 130]);
    expect(Array.from(live.at(-1)!)).toEqual([172]);
  });

  it("overflow'da split ANSI unit'i retention'a almaz; replay yarım escape ile başlamaz", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const live: Uint8Array[] = [];
    session.onOutput((data) => live.push(data));
    const emit = (data: number[]) => handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-1", data } });
    emit([36, 32]);
    emit(new Array<number>(256 * 1024 - 2).fill(97));
    emit([27, 91, 51, 49]);
    emit([109]);
    const replay: Uint8Array[] = [];
    session.onOutput((data) => replay.push(data));

    expect(Array.from(replay[0])).toEqual([36, 32]);
    expect(replay.reduce((total, data) => total + data.byteLength, 0)).toBe(256 * 1024);
    expect(replay.every((data) => !data.includes(27))).toBe(true);
    expect(Array.from(live.at(-2)!)).toEqual([27, 91, 51, 49]);
    expect(Array.from(live.at(-1)!)).toEqual([109]);
  });

  it("clearRetention eski replay epoch'unu siler ve sonraki güvenli output ile yenisini başlatır", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const emit = (data: number[]) => handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-1", data } });
    emit([111, 108, 100]);
    session.clearRetention();
    emit([110, 101, 119]);
    const replay: number[] = [];
    session.onOutput((data) => replay.push(...data));

    expect(replay).toEqual([110, 101, 119]);
  });

  it("eşzamanlı close çağrılarını tek terminal_kapat promise'ında birleştirir", async () => {
    listen.mockResolvedValue(vi.fn());
    let finishClose!: () => void;
    invoke.mockImplementation((command: string) => {
      if (command === "terminal_ac") {
        return Promise.resolve({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
      }
      if (command === "terminal_kapat") return new Promise<void>((resolve) => { finishClose = resolve; });
      return Promise.resolve();
    });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);

    const first = session.close();
    const second = session.close();
    expect(invoke.mock.calls.filter(([command]) => command === "terminal_kapat")).toHaveLength(1);
    finishClose();
    await Promise.all([first, second]);
  });

  it("ikinci listener kurulamazsa daha önce kurulan listener'ı rollback eder", async () => {
    const stopOutput = vi.fn();
    listen
      .mockResolvedValueOnce(stopOutput)
      .mockRejectedValueOnce(new Error("closed listener kurulamadı"));

    await expect(createTerminalRuntime().openSession("/repo", 80, 24))
      .rejects.toThrow("closed listener kurulamadı");

    expect(stopOutput).toHaveBeenCalledOnce();
    expect(invoke).not.toHaveBeenCalled();
  });

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

  it("retained transcript'i 256 KiB ile sınırlar ve güvenli akış başlangıcını korur", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    for (let index = 0; index < 257; index += 1) {
      const data = new Array<number>(1024).fill(97);
      handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-1", data } });
    }
    const replayed: Uint8Array[] = [];
    session.onOutput((data) => replayed.push(data));

    expect(replayed).toHaveLength(256);
    expect(replayed[0][0]).toBe(97);
    expect(replayed[255][0]).toBe(97);
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
