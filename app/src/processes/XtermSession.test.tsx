import { StrictMode } from "react";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const { bridgeInvoke, bridgeListen } = vi.hoisted(() => ({ bridgeInvoke: vi.fn(), bridgeListen: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: bridgeInvoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: bridgeListen }));

import { createTerminalRuntime, type TerminalSession } from "./terminalBridge";

vi.mock("@xterm/xterm", () => ({ Terminal: vi.fn() }));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: vi.fn() }));
vi.mock("@xterm/addon-webgl", () => ({ WebglAddon: vi.fn() }));

import { XtermSession, type XtermAdapter } from "./XtermSession";

afterEach(cleanup);

function setup() {
  let dataHandler: ((data: string) => void) | undefined;
  let outputHandler: ((data: Uint8Array) => void) | undefined;
  const adapter: XtermAdapter = {
    clear: vi.fn(), dispose: vi.fn(), focus: vi.fn(), fit: vi.fn(() => ({ cols: 111, rows: 33 })),
    getSelection: vi.fn(() => "seçim"), open: vi.fn(), paste: vi.fn(), write: vi.fn(),
    onData: vi.fn((handler) => { dataHandler = handler; return vi.fn(); }),
  };
  const session: TerminalSession = {
    snapshot: { terminalId: "terminal-1", cwd: "/repo", cols: 80, rows: 24, pid: 42 },
    write: vi.fn(async () => undefined), resize: vi.fn(async () => undefined), close: vi.fn(async () => undefined),
    clearRetention: vi.fn(),
    onOutput: vi.fn((handler) => { outputHandler = handler; return vi.fn(); }),
    onClosed: vi.fn(() => vi.fn()), dispose: vi.fn(),
  };
  return { adapter, data: (value: string) => dataHandler?.(value), output: (value: number[]) => outputHandler?.(new Uint8Array(value)), session };
}

describe("XtermSession", () => {
  it("handshake-buffered ilk prompt'u StrictMode ikinci fresh adapter'ına da replay eder", async () => {
    const handlers = new Map<string, (event: { payload: unknown }) => void>();
    bridgeListen.mockImplementation(async (name: string, handler: (event: { payload: unknown }) => void) => {
      handlers.set(name, handler);
      return vi.fn();
    });
    bridgeInvoke.mockImplementation(async (command: string) => {
      if (command === "terminal_ac") {
        handlers.get("terminal://cikti")?.({ payload: { terminalId: "terminal-fast", data: [36, 32] } });
        return { terminalId: "terminal-fast", cwd: "/repo", cols: 80, rows: 24, pid: 42 };
      }
    });
    const session = await createTerminalRuntime().openSession("/repo", 80, 24);
    const adapters = [setup().adapter, setup().adapter];
    const createAdapter = vi.fn(() => adapters.shift()!);

    render(<StrictMode><XtermSession active createAdapter={createAdapter} session={session} /></StrictMode>);

    await waitFor(() => expect(createAdapter).toHaveBeenCalledTimes(2));
    expect(createAdapter.mock.results[0].value.write).toHaveBeenCalledWith("$ ");
    expect(createAdapter.mock.results[1].value.write).toHaveBeenCalledWith("$ ");
  });

  it("StrictMode çift effect döngüsünde fresh adapter ile input ve output'u sürdürür", async () => {
    const value = setup();
    const adapters = [setup().adapter, setup().adapter];
    const createAdapter = vi.fn(() => adapters.shift()!);
    render(
      <StrictMode>
        <XtermSession active createAdapter={createAdapter} session={value.session} />
      </StrictMode>,
    );

    await waitFor(() => expect(createAdapter).toHaveBeenCalledTimes(2));
    const liveAdapter = createAdapter.mock.results[1].value;
    const liveInput = vi.mocked(liveAdapter.onData).mock.calls[0][0];
    liveInput("ok");
    await waitFor(() => expect(value.session.write).toHaveBeenCalled());
    value.output([36, 32]);
    expect(liveAdapter.write).toHaveBeenCalledWith("$ ");
    expect(createAdapter.mock.results[0].value.dispose).toHaveBeenCalledOnce();
    expect(liveAdapter.dispose).not.toHaveBeenCalled();
  });

  it("xterm klavye verisini UTF-8 baytları olarak terminale yazar ve Ctrl+C'yi React'te kesmez", async () => {
    const value = setup();
    const view = render(<XtermSession active adapter={value.adapter} session={value.session} />);
    value.data("ş\u0003");
    const keydown = new KeyboardEvent("keydown", { key: "c", ctrlKey: true, bubbles: true, cancelable: true });
    view.getByLabelText("Terminal ekranı").dispatchEvent(keydown);

    await waitFor(() => expect(value.session.write).toHaveBeenCalled());
    const [bytes] = vi.mocked(value.session.write).mock.calls[0];
    expect(Array.from(bytes)).toEqual([197, 159, 3]);
    expect(keydown.defaultPrevented).toBe(false);
  });

  it("fit boyutlarını runtime'a yollar ve etkinleşince terminali odaklar", async () => {
    const value = setup();
    render(<XtermSession active adapter={value.adapter} session={value.session} />);
    await waitFor(() => expect(value.session.resize).toHaveBeenCalledWith(111, 33));
    expect(value.adapter.focus).toHaveBeenCalled();
  });

  it("parçalanmış UTF-8 çıktıyı birleştirip ANSI dizisini değiştirmeden xterm'e yazar", async () => {
    const value = setup();
    render(<XtermSession active adapter={value.adapter} session={value.session} />);
    await waitFor(() => expect(value.session.onOutput).toHaveBeenCalled());
    value.output([27, 91, 51, 49, 109, 226, 130]);
    value.output([172, 27, 91, 48, 109]);
    expect(value.adapter.write).toHaveBeenNthCalledWith(1, "\u001b[31m");
    expect(value.adapter.write).toHaveBeenNthCalledWith(2, "€\u001b[0m");
  });

  it("unmount sırasında xterm ve output aboneliğini kapatır ama owner session'ını dispose etmez", async () => {
    const value = setup();
    const stopOutput = vi.fn();
    vi.mocked(value.session.onOutput).mockReturnValue(stopOutput);
    const view = render(<XtermSession active adapter={value.adapter} session={value.session} />);
    view.unmount();
    expect(stopOutput).toHaveBeenCalledOnce();
    expect(value.adapter.dispose).toHaveBeenCalledOnce();
    expect(value.session.dispose).not.toHaveBeenCalled();
  });

  it("temizle, kopyala, yapıştır ve kapanma durumunu erişilebilir denetimlerle sunar", async () => {
    const value = setup();
    const writeText = vi.fn(async () => undefined);
    const readText = vi.fn(async () => "panodan");
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { readText, writeText } });
    const view = render(<XtermSession active adapter={value.adapter} closed={{ reason: "shell exited", exitCode: 1 }} session={value.session} />);
    fireEvent.click(view.getByRole("button", { name: "Terminali temizle" }));
    fireEvent.click(view.getByRole("button", { name: "Seçimi kopyala" }));
    fireEvent.click(view.getByRole("button", { name: "Panodan yapıştır" }));
    await waitFor(() => expect(value.adapter.paste).toHaveBeenCalledWith("panodan"));
    expect(value.adapter.clear).toHaveBeenCalledOnce();
    expect(value.session.clearRetention).toHaveBeenCalledOnce();
    expect(writeText).toHaveBeenCalledWith("seçim");
    expect(view.getByRole("status").textContent).toContain("çıkış kodu: 1");
  });

  it("temizle yalnız mevcut xterm ekranını siler ve transcript'i kendiliğinden replay etmez", () => {
    const value = setup();
    const view = render(<XtermSession active adapter={value.adapter} session={value.session} />);
    value.output([36, 32]);
    expect(value.adapter.write).toHaveBeenCalledTimes(1);
    fireEvent.click(view.getByRole("button", { name: "Terminali temizle" }));
    expect(value.adapter.clear).toHaveBeenCalledOnce();
    expect(value.adapter.write).toHaveBeenCalledTimes(1);
  });
  it("aynı boyut için çekirdeğe tekrar resize göndermez", async () => {
    const { adapter, session } = setup();
    render(<XtermSession active session={session} adapter={adapter} />);

    await waitFor(() => expect(session.resize).toHaveBeenCalledWith(111, 33));
    const ilk = (session.resize as ReturnType<typeof vi.fn>).mock.calls.length;

    // Aynı ölçüm yeniden gelirse IPC tekrarlanmamalı: pencere sürüklenirken
    // saniyede onlarca kez tetiklenip terminali takıyordu.
    (adapter.fit as ReturnType<typeof vi.fn>).mockReturnValue({ cols: 111, rows: 33 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect((session.resize as ReturnType<typeof vi.fn>).mock.calls.length).toBe(ilk);
  });

  it("sıfır ölçümde çekirdeğe boyut bildirmez", async () => {
    const { adapter, session } = setup();
    (adapter.fit as ReturnType<typeof vi.fn>).mockReturnValue({ cols: 0, rows: 0 });

    render(<XtermSession active session={session} adapter={adapter} />);
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(session.resize).not.toHaveBeenCalled();
  });
});
