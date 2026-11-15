import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke, listen, channels } = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
  channels: [] as Array<{ onmessage: (message: unknown) => void }>,
}));

// Gerçek Channel Tauri çalışma zamanına bağlıdır; sahte sürüm `onmessage`'i dışarı verir.
vi.mock("@tauri-apps/api/core", () => ({
  invoke,
  Channel: class {
    onmessage: (message: unknown) => void = () => undefined;
    constructor() { channels.push(this); }
  },
}));
vi.mock("@tauri-apps/api/event", () => ({ listen }));

import { createTerminalRuntime } from "./terminalBridge";

beforeEach(() => {
  invoke.mockReset();
  listen.mockReset();
  channels.length = 0;
});

/** Rust'ın kanala yolladığı ham baytı (ArrayBuffer) en son açılan terminalin kanalına verir. */
function emitOutput(data: number[]) {
  channels.at(-1)!.onmessage(new Uint8Array(data).buffer);
}

describe("terminalBridge", () => {
  async function openOutputHarness() {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    return { emit: emitOutput, session };
  }

  it("limit üstü unterminated OSC retention'ı dondurur; clear yeni epoch'u temiz parser ile açar", async () => {
    const { emit, session } = await openOutputHarness();
    let liveBytes = 0;
    let lastLive: number[] = [];
    session.onOutput((data) => {
      liveBytes += data.byteLength;
      lastLive = Array.from(data);
    });

    emit([112, 114, 111, 109, 112, 116, 32]);
    emit([27, 93, ...new Array<number>(256 * 1024).fill(97)]);
    emit([108, 105, 118, 101]);
    const frozenReplay: number[] = [];
    session.onOutput((data) => frozenReplay.push(...data));
    expect(frozenReplay).toEqual([112, 114, 111, 109, 112, 116, 32]);
    expect(liveBytes).toBe(7 + 2 + 256 * 1024 + 4);
    expect(lastLive).toEqual([108, 105, 118, 101]);
    session.clearRetention();
    emit([110, 101, 119]);
    const clearedReplay: number[] = [];
    session.onOutput((data) => clearedReplay.push(...data));

    expect(clearedReplay).toEqual([110, 101, 119]);
  });

  it("limit üstü unterminated DCS retention'ı dondurur; clear parser state'ini tamamen sıfırlar", async () => {
    const { emit, session } = await openOutputHarness();

    emit([36, 32]);
    emit([27, 80, ...new Array<number>(256 * 1024).fill(113)]);
    session.clearRetention();
    emit([111, 107]);
    const replay: number[] = [];
    session.onOutput((data) => replay.push(...data));

    expect(replay).toEqual([111, 107]);
  });

  it("clear yarım UTF-8 unit'ini atar ve sonraki ASCII'yi yeni epoch'un başı yapar", async () => {
    const { emit, session } = await openOutputHarness();

    emit([226, 130]);
    session.clearRetention();
    emit([36, 32]);
    const replay: number[] = [];
    session.onOutput((data) => replay.push(...data));

    expect(replay).toEqual([36, 32]);
  });

  it("clear pending ANSI unit'ini ve frozen/parser state'ini atıp bağımsız epoch açar", async () => {
    const { emit, session } = await openOutputHarness();

    emit([27, 91, 51, 49]);
    session.clearRetention();
    emit([109, 114, 101, 97, 100, 121]);
    const replay: number[] = [];
    session.onOutput((data) => replay.push(...data));

    expect(replay).toEqual([109, 114, 101, 97, 100, 121]);
  });

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
    const emit = emitOutput;
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
    const emit = emitOutput;
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
    const emit = emitOutput;
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
      if (command === "terminal_ac_kanal") {
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

  it("kapanma dinleyicisi kurulamazsa terminal açılmaz", async () => {
    listen.mockRejectedValueOnce(new Error("closed listener kurulamadı"));

    await expect(createTerminalRuntime().openSession("/repo", 80, 24))
      .rejects.toThrow("closed listener kurulamadı");

    expect(invoke).not.toHaveBeenCalled();
  });

  it("terminal açılamazsa kapanma dinleyicisini bırakır", async () => {
    const stopClosed = vi.fn();
    listen.mockResolvedValue(stopClosed);
    invoke.mockRejectedValue(new Error("pty açılamadı"));

    await expect(createTerminalRuntime().openSession("/repo", 80, 24)).rejects.toThrow("pty açılamadı");

    expect(stopClosed).toHaveBeenCalledOnce();
  });

  /* Ölçüldü (30 Ekim): çıktı `terminal://cikti` olayında JSON sayı dizisiydi (her bayt ayrı bir
     JSON sayısı + kimlik süzmesi). Artık terminale özgü Channel'dan ham ArrayBuffer gelir. */
  it("çıktı ham ArrayBuffer olarak kanaldan gelir ve olay dinleyicisi çıktı için kurulmaz", async () => {
    listen.mockResolvedValue(vi.fn());
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const alinan: Uint8Array[] = [];
    session.onOutput((data) => alinan.push(data));

    emitOutput([0x1b, 0x5b, 0x33, 0x31, 0x6d, 0xff]);

    expect(alinan).toEqual([new Uint8Array([0x1b, 0x5b, 0x33, 0x31, 0x6d, 0xff])]);
    expect(listen.mock.calls.map(([name]) => name)).toEqual(["terminal://kapandi"]);
  });

  it("terminal_ac_kanal dönmeden gelen ilk çıktıyı kanaldan alıp abonelere tekrarlar", async () => {
    listen.mockResolvedValue(vi.fn());
    invoke.mockImplementation(async (command: string) => {
      if (command === "terminal_ac_kanal") {
        emitOutput([36, 32]);
        return { terminalId: "terminal-fast", cwd: "/repo", cols: 80, rows: 24, pid: 42 };
      }
    });

    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const output = vi.fn();
    session.onOutput(output);

    expect(output).toHaveBeenCalledWith(new Uint8Array([36, 32]));
    expect(listen.mock.invocationCallOrder[0]).toBeLessThan(invoke.mock.invocationCallOrder[0]);
  });

  it("dispose sonrası gelen kanal iletisi abonelere ve dökümlere işlenmez", async () => {
    listen.mockResolvedValue(vi.fn());
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    session.dispose();
    emitOutput([97]);
    const replay = vi.fn();
    session.onOutput(replay);

    expect(replay).not.toHaveBeenCalled();
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
      emitOutput(data);
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
      if (command === "terminal_ac_kanal") {
        handlers.get("terminal://kapandi")?.({ payload: { terminalId: "terminal-fast", reason: "shell exited", exitCode: 1 } });
        return { terminalId: "terminal-fast", cwd: "/repo", cols: 80, rows: 24, pid: 42 };
      }
    });

    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const closed = vi.fn();
    session.onClosed(closed);
    await session.close();

    expect(closed).toHaveBeenCalledWith({ reason: "shell exited", exitCode: 1 });
    expect(invoke.mock.calls).toEqual([["terminal_ac_kanal", { cwd: "/repo", cols: 80, rows: 24, output: channels[0] }]]);
  });

  it("Tauri terminal komutlarını kesin ad ve payload ile çağırır", async () => {
    invoke.mockResolvedValueOnce({ terminalId: "terminal-7", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const runtime = createTerminalRuntime();
    const onOutput = vi.fn();

    await expect(runtime.open("/repo", 80, 24, onOutput)).resolves.toEqual({
      terminalId: "terminal-7", cwd: "/repo", cols: 80, rows: 24, pid: 42,
    });
    await runtime.write("terminal-7", new Uint8Array([3, 10]));
    await runtime.resize("terminal-7", 120, 36);
    await runtime.close("terminal-7");
    emitOutput([226, 130]);

    expect(invoke.mock.calls).toEqual([
      ["terminal_ac_kanal", { cwd: "/repo", cols: 80, rows: 24, output: channels[0] }],
      // U4-25: girdi sayı dizisi değil HAM bayt; kimlik başlıkta.
      ["terminal_yaz", new Uint8Array([3, 10]), { headers: { "x-terminal-id": "terminal-7" } }],
      ["terminal_boyutla", { terminalId: "terminal-7", cols: 120, rows: 36 }],
      ["terminal_kapat", { terminalId: "terminal-7" }],
    ]);
    expect(onOutput).toHaveBeenCalledWith(new Uint8Array([226, 130]));
  });

  it("kapanma olayını süzer ve dönen işlevle dinleyiciyi kaldırır", async () => {
    const closedUnlisten = vi.fn();
    listen.mockImplementation(async (_name: string, handler: (event: { payload: unknown }) => void) => {
      handler({ payload: { terminalId: "terminal-3", reason: "başkası", exitCode: 9 } });
      handler({ payload: { terminalId: "terminal-2", reason: "çıktı", exitCode: 0 } });
      return closedUnlisten;
    });
    const runtime = createTerminalRuntime();
    const onClosed = vi.fn();

    const stopClosed = await runtime.onClosed("terminal-2", onClosed);
    stopClosed();

    expect(listen.mock.calls.map(([name]) => name)).toEqual(["terminal://kapandi"]);
    expect(onClosed).toHaveBeenCalledTimes(1);
    expect(onClosed).toHaveBeenCalledWith({ reason: "çıktı", exitCode: 0 });
    expect(closedUnlisten).toHaveBeenCalledOnce();
  });

  it("kapanma olayında exit code'u session abonelerine taşır", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    listen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    invoke.mockResolvedValue({ terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const closed = vi.fn();
    session.onClosed(closed);

    handlers.get("terminal://kapandi")?.({ payload: { terminalId: "terminal-1", reason: "süreç kapandı", exitCode: 1 } });

    expect(closed).toHaveBeenCalledWith({ reason: "süreç kapandı", exitCode: 1 });
  });
});
