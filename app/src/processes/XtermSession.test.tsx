import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TerminalRuntime } from "./terminalBridge";

vi.mock("@xterm/xterm", () => ({ Terminal: vi.fn() }));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: vi.fn() }));

import { XtermSession, type XtermAdapter } from "./XtermSession";

afterEach(cleanup);

function setup() {
  let dataHandler: ((data: string) => void) | undefined;
  let outputHandler: ((data: Uint8Array) => void) | undefined;
  let closedHandler: ((reason: string) => void) | undefined;
  const adapter: XtermAdapter = {
    clear: vi.fn(), dispose: vi.fn(), focus: vi.fn(), fit: vi.fn(() => ({ cols: 111, rows: 33 })),
    getSelection: vi.fn(() => "seçim"), open: vi.fn(), paste: vi.fn(), write: vi.fn(),
    onData: vi.fn((handler) => { dataHandler = handler; return vi.fn(); }),
  };
  const runtime: TerminalRuntime = {
    open: vi.fn(), write: vi.fn(async () => undefined), resize: vi.fn(async () => undefined), close: vi.fn(async () => undefined),
    onOutput: vi.fn(async (_id, handler) => { outputHandler = handler; return vi.fn(); }),
    onClosed: vi.fn(async (_id, handler) => { closedHandler = handler; return vi.fn(); }),
  };
  return { adapter, closed: (reason: string) => closedHandler?.(reason), data: (value: string) => dataHandler?.(value), output: (value: number[]) => outputHandler?.(new Uint8Array(value)), runtime };
}

describe("XtermSession", () => {
  it("xterm klavye verisini UTF-8 baytları olarak terminale yazar ve Ctrl+C'yi React'te kesmez", async () => {
    const value = setup();
    const view = render(<XtermSession active adapter={value.adapter} runtime={value.runtime} terminalId="terminal-1" />);
    value.data("ş\u0003");
    const keydown = new KeyboardEvent("keydown", { key: "c", ctrlKey: true, bubbles: true, cancelable: true });
    view.getByLabelText("Terminal ekranı").dispatchEvent(keydown);

    await waitFor(() => expect(value.runtime.write).toHaveBeenCalled());
    const [terminalId, bytes] = vi.mocked(value.runtime.write).mock.calls[0];
    expect(terminalId).toBe("terminal-1");
    expect(Array.from(bytes)).toEqual([197, 159, 3]);
    expect(keydown.defaultPrevented).toBe(false);
  });

  it("fit boyutlarını runtime'a yollar ve etkinleşince terminali odaklar", async () => {
    const value = setup();
    render(<XtermSession active adapter={value.adapter} runtime={value.runtime} terminalId="terminal-1" />);
    await waitFor(() => expect(value.runtime.resize).toHaveBeenCalledWith("terminal-1", 111, 33));
    expect(value.adapter.focus).toHaveBeenCalled();
  });

  it("parçalanmış UTF-8 çıktıyı birleştirip ANSI dizisini değiştirmeden xterm'e yazar", async () => {
    const value = setup();
    render(<XtermSession active adapter={value.adapter} runtime={value.runtime} terminalId="terminal-1" />);
    await waitFor(() => expect(value.runtime.onOutput).toHaveBeenCalled());
    value.output([27, 91, 51, 49, 109, 226, 130]);
    value.output([172, 27, 91, 48, 109]);
    expect(value.adapter.write).toHaveBeenNthCalledWith(1, "\u001b[31m");
    expect(value.adapter.write).toHaveBeenNthCalledWith(2, "€\u001b[0m");
  });

  it("unmount sırasında xterm ve iki olay dinleyicisini kapatır", async () => {
    const value = setup();
    const stopOutput = vi.fn();
    const stopClosed = vi.fn();
    vi.mocked(value.runtime.onOutput).mockResolvedValue(stopOutput);
    vi.mocked(value.runtime.onClosed).mockResolvedValue(stopClosed);
    const view = render(<XtermSession active adapter={value.adapter} runtime={value.runtime} terminalId="terminal-1" />);
    await waitFor(() => expect(value.runtime.onClosed).toHaveBeenCalled());
    view.unmount();
    expect(stopOutput).toHaveBeenCalledOnce();
    expect(stopClosed).toHaveBeenCalledOnce();
    expect(value.adapter.dispose).toHaveBeenCalledOnce();
  });

  it("temizle, kopyala, yapıştır ve kapanma durumunu erişilebilir denetimlerle sunar", async () => {
    const value = setup();
    const writeText = vi.fn(async () => undefined);
    const readText = vi.fn(async () => "panodan");
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { readText, writeText } });
    const view = render(<XtermSession active adapter={value.adapter} runtime={value.runtime} terminalId="terminal-1" />);
    fireEvent.click(view.getByRole("button", { name: "Terminali temizle" }));
    fireEvent.click(view.getByRole("button", { name: "Seçimi kopyala" }));
    fireEvent.click(view.getByRole("button", { name: "Panodan yapıştır" }));
    await waitFor(() => expect(value.adapter.paste).toHaveBeenCalledWith("panodan"));
    expect(value.adapter.clear).toHaveBeenCalledOnce();
    expect(writeText).toHaveBeenCalledWith("seçim");
    act(() => value.closed("shell exited"));
    expect(view.getByRole("status").textContent).toContain("shell exited");
  });
});
