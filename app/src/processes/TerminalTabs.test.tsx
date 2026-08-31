import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TerminalRuntime, TerminalSession } from "./terminalBridge";

vi.mock("./XtermSession", () => ({
  XtermSession: ({ session, active }: { session: TerminalSession; active: boolean }) => (
    <div data-active={String(active)}>xterm {session.snapshot.terminalId}</div>
  ),
}));

import { TerminalTabs } from "./TerminalTabs";

afterEach(cleanup);

function runtime(): TerminalRuntime & { sessions: Array<TerminalSession & { emitClosed(event: { reason: string; exitCode: number | null }): void }> } {
  let id = 0;
  const sessions: Array<TerminalSession & { emitClosed(event: { reason: string; exitCode: number | null }): void }> = [];
  const value = {
    open: vi.fn(async (cwd, cols, rows) => ({ terminalId: `terminal-${++id}`, cwd, cols, rows, pid: 100 + id })),
    write: vi.fn(async () => undefined), resize: vi.fn(async () => undefined), close: vi.fn(async () => undefined),
    onOutput: vi.fn(async () => vi.fn()), onClosed: vi.fn(async () => vi.fn()),
    openSession: vi.fn(async (cwd: string, cols: number, rows: number) => {
      const terminalId = `terminal-${++id}`;
      const closedHandlers = new Set<(event: { reason: string; exitCode: number | null }) => void>();
      const session: TerminalSession & { emitClosed(event: { reason: string; exitCode: number | null }): void } = {
        snapshot: { terminalId, cwd, cols, rows, pid: 100 + id },
        write: vi.fn(async () => undefined), resize: vi.fn(async () => undefined), close: vi.fn(async () => undefined),
        clearRetention: vi.fn(),
        onOutput: vi.fn(() => vi.fn()),
        onClosed: vi.fn((handler) => { closedHandlers.add(handler); return () => closedHandlers.delete(handler); }),
        dispose: vi.fn(),
        emitClosed: (event) => closedHandlers.forEach((handler) => handler(event)),
      };
      sessions.push(session);
      return session;
    }),
    sessions,
  } as TerminalRuntime & { sessions: Array<TerminalSession & { emitClosed(event: { reason: string; exitCode: number | null }): void }> };
  return value;
}

describe("TerminalTabs", () => {
  it("Yeni terminal ile kullanıcı shell'ini etkin workspace cwd'sinde açar", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/Projects/fusion-cli" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    await waitFor(() => expect(value.openSession).toHaveBeenCalledWith("/Projects/fusion-cli", 80, 24));
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
    await waitFor(() => expect(value.sessions[1].close).toHaveBeenCalledOnce());
    expect(screen.queryByRole("tab", { name: "Terminal 2" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Terminal 1" }).getAttribute("aria-selected")).toBe("true");
  });

  it("terminal açma hatasını alert olarak gösterir", async () => {
    const value = runtime();
    vi.mocked(value.openSession).mockRejectedValueOnce(new Error("pty açılamadı"));
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    expect((await screen.findByRole("alert")).textContent).toContain("pty açılamadı");
  });

  it("doğal kapanışı sekme durumuna taşır ve kapalı sekmeyi backend close olmadan kaldırır", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    const tab = await screen.findByRole("tab", { name: "Terminal 1" });
    value.sessions[0].emitClosed({ reason: "shell exited", exitCode: 0 });
    await waitFor(() => expect(tab.textContent).toContain("Bitti"));

    fireEvent.click(screen.getByRole("button", { name: "Aktif terminali kapat" }));
    await waitFor(() => expect(screen.queryByRole("tab", { name: "Terminal 1" })).toBeNull());
    expect(value.sessions[0].close).not.toHaveBeenCalled();
    expect(value.sessions[0].dispose).toHaveBeenCalledOnce();
  });

  it("başarısız doğal kapanışı kırmızı hata koduyla gösterir", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    const tab = await screen.findByRole("tab", { name: "Terminal 1" });

    value.sessions[0].emitClosed({ reason: "süreç kapandı", exitCode: 1 });

    await waitFor(() => expect(tab.textContent).toContain("Hata (1)"));
    expect(tab.querySelector(".terminal-tabs__dot--hata")).not.toBeNull();
  });

  it("kullanıcı kapatmasını nötr durduruldu durumu olarak gösterir", async () => {
    const value = runtime();
    render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    const tab = await screen.findByRole("tab", { name: "Terminal 1" });

    value.sessions[0].emitClosed({ reason: "kullanıcı kapattı", exitCode: null });

    await waitFor(() => expect(tab.textContent).toContain("Durduruldu"));
    expect(tab.querySelector(".terminal-tabs__dot--durduruldu")).not.toBeNull();
  });

  it("owner unmount sırasında çalışan bütün PTY'leri tam birer kez kapatır", async () => {
    const value = runtime();
    const view = render(<TerminalTabs cwd="/repo" runtime={value} />);
    const create = screen.getByRole("button", { name: "Yeni terminal" });
    fireEvent.click(create);
    await screen.findByRole("tab", { name: "Terminal 1" });
    fireEvent.click(create);
    await screen.findByRole("tab", { name: "Terminal 2" });
    view.unmount();

    await waitFor(() => {
      expect(value.sessions[0].close).toHaveBeenCalledOnce();
      expect(value.sessions[1].close).toHaveBeenCalledOnce();
    });
    expect(value.sessions[0].dispose).toHaveBeenCalledOnce();
    expect(value.sessions[1].dispose).toHaveBeenCalledOnce();
  });

  it("open handshake sürerken unmount olursa sonradan açılan PTY'yi kapatır", async () => {
    const value = runtime();
    let resolve!: (session: TerminalSession) => void;
    vi.mocked(value.openSession).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const view = render(<TerminalTabs cwd="/repo" runtime={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    view.unmount();
    const late = await runtime().openSession("/repo", 80, 24);
    resolve(late);

    await waitFor(() => expect(late.close).toHaveBeenCalledOnce());
    expect(late.dispose).toHaveBeenCalledOnce();
  });
});
