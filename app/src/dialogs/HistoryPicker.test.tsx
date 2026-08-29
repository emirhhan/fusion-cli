import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoryPicker } from "./HistoryPicker";
import type { HistoryController } from "../history/useHistory";

afterEach(cleanup);

function controller(overrides: Partial<HistoryController> = {}): HistoryController {
  return {
    error: null,
    loadMoreSessions: vi.fn(async () => undefined),
    loadMoreTurns: vi.fn(async () => undefined),
    loading: false,
    openSource: vi.fn(async () => undefined),
    selected: null,
    selectSession: vi.fn(async () => undefined),
    sessionCursor: null,
    sessions: [],
    source: null,
    sources: [{ ad: "claude", komut: "/resumeclaude" }],
    turnCursor: null,
    turns: [],
    ...overrides,
  };
}

describe("HistoryPicker", () => {
  it("yalnız keşfedilen kaynakları gösterir ve seçim olmadan devralmaz", () => {
    const history = controller();
    render(
      <HistoryPicker
        history={history}
        onClose={vi.fn()}
        onResume={vi.fn()}
        open
      />,
    );

    expect(screen.getByRole("button", { name: "Claude" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Hermes" })).toBeNull();
    expect(screen.getByRole("button", { name: "Bu konuşmayı devral" })).toHaveProperty(
      "disabled",
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Claude" }));
    expect(history.openSource).toHaveBeenCalledWith("claude");
  });

  it("önizlemeyi gösterir ve hassas değerleri sakin bir uyarıyla bildirir", async () => {
    const session = {
      kaynak: "codex" as const,
      oturum_id: "cx1",
      baslik: "Fusion uygulaması",
      guncellendi: 100,
      tur_sayisi: 4,
      boyut: 200,
    };
    const history = controller({
      source: "codex",
      selected: session,
      sessions: [session],
      turns: [
        { rol: "user", metin: "Uygulamayı yap", zaman: 10 },
        { rol: "assistant", metin: "Başlıyorum", zaman: 11 },
      ],
    });
    const onResume = vi.fn(async () => ({ id: "new", secretCount: 2 }));
    render(
      <HistoryPicker history={history} onClose={vi.fn()} onResume={onResume} open />,
    );

    expect(screen.getByText("Uygulamayı yap")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bu konuşmayı devral" }));
    await waitFor(() => expect(onResume).toHaveBeenCalledWith(session));
    expect(await screen.findByText(/2 hassas değer/i)).toBeTruthy();
  });
});
