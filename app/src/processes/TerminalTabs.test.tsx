import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TerminalRuntime } from "./terminalBridge";

vi.mock("./XtermSession", () => ({
  XtermSession: ({ terminalId, active }: { terminalId: string; active: boolean }) => (
    <div data-active={String(active)}>xterm {terminalId}</div>
  ),
}));

import { TerminalTabs } from "./TerminalTabs";

afterEach(cleanup);

function runtime(): TerminalRuntime {
  let id = 0;
  return {
    open: vi.fn(async (cwd, cols, rows) => ({ terminalId: `terminal-${++id}`, cwd, cols, rows, pid: 100 + id })),
    write: vi.fn(async () => undefined), resize: vi.fn(async () => undefined), close: vi.fn(async () => undefined),
    onOutput: vi.fn(async () => vi.fn()), onClosed: vi.fn(async () => vi.fn()),
  };
}

describe("TerminalTabs", () => {
  it("Yeni terminal ile kullanıcı shell'ini etkin workspace cwd'sinde açar", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/Projects/fusion-cli" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    await waitFor(() => expect(value.open).toHaveBeenCalledWith("/Projects/fusion-cli", 80, 24));
    expect(screen.getByRole("tab", { name: "Terminal 1" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("xterm terminal-1").getAttribute("data-active")).toBe("true");
    expect(screen.queryByRole("textbox", { name: "Terminal komutu" })).toBeNull();
  });

  it("birden çok terminali korur ve ok/Home/End ile erişilebilir biçimde seçer", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    const create = screen.getByRole("button", { name: "Yeni terminal" });
    fireEvent.click(create);
    await screen.findByRole("tab", { name: "Terminal 1" });
    fireEvent.click(create);
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(2));
    const second = screen.getByRole("tab", { name: "Terminal 2" });
    fireEvent.keyDown(second, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Terminal 1" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Terminal 1" }), { key: "End" });
    expect(second.getAttribute("aria-selected")).toBe("true");
  });

  it("aktif sekmeyi runtime üzerinden kapatıp komşu terminale geçer", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    const create = screen.getByRole("button", { name: "Yeni terminal" });
    fireEvent.click(create);
    await screen.findByRole("tab", { name: "Terminal 1" });
    fireEvent.click(create);
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "Aktif terminali kapat" }));
    await waitFor(() => expect(value.close).toHaveBeenCalledWith("terminal-2"));
    expect(screen.queryByRole("tab", { name: "Terminal 2" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Terminal 1" }).getAttribute("aria-selected")).toBe("true");
  });

  it("terminal açma hatasını alert olarak gösterir", async () => {
    const value = runtime();
    vi.mocked(value.open).mockRejectedValueOnce(new Error("pty açılamadı"));
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    expect((await screen.findByRole("alert")).textContent).toContain("pty açılamadı");
  });
});
