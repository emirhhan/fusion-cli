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
    searchNotice: "",
    searchPartial: false,
    searchQuery: "",
    searchResults: [],
    searchSessions: vi.fn(async () => undefined),
    searching: false,
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

  it("arama kutusu çekirdeğe sorar; yerelde filtrelemez", async () => {
    const history = controller({ source: "claude" });
    render(<HistoryPicker history={history} onClose={vi.fn()} onResume={vi.fn()} open />);

    fireEvent.change(screen.getByRole("searchbox", { name: "Geçmiş konuşmalarda ara" }), {
      target: { value: "game" },
    });

    await waitFor(() => expect(history.searchSessions).toHaveBeenCalledWith("game"));
  });

  it("arama sonucunda eşleşmenin geçtiği parçayı gösterir", () => {
    const history = controller({
      source: "claude",
      searchQuery: "game",
      searchResults: [
        {
          kaynak: "claude" as const,
          oturum_id: "eski",
          baslik: "2026-01-01 · 40 bayt",
          guncellendi: 100,
          tur_sayisi: 4,
          boyut: 40,
          baslikta: false,
          parca: "…tabii, game loop kuruyorum",
        },
      ],
    });
    render(<HistoryPicker history={history} onClose={vi.fn()} onResume={vi.fn()} open />);

    expect(screen.getByText("…tabii, game loop kuruyorum")).toBeTruthy();
    expect(screen.queryByText("Bu kaynakta gösterilecek konuşma bulunamadı.")).toBeNull();
  });

  it("kesilen aramayı bildirir; sessizce sonuç yok demez", () => {
    const history = controller({
      source: "claude",
      searchQuery: "game",
      searchResults: [],
      searchPartial: true,
      searchNotice: "Arama süre bütçesi doldu; tarama yarıda kesildi.",
    });
    render(<HistoryPicker history={history} onClose={vi.fn()} onResume={vi.fn()} open />);

    expect(screen.getByText("Arama süre bütçesi doldu; tarama yarıda kesildi.")).toBeTruthy();
  });

  it("arama sonucu boşsa aramaya özgü mesaj gösterir", () => {
    const history = controller({ source: "claude", searchQuery: "yokböylesi", searchResults: [] });
    render(<HistoryPicker history={history} onClose={vi.fn()} onResume={vi.fn()} open />);

    expect(screen.getByText("“yokböylesi” ile eşleşen konuşma bulunamadı.")).toBeTruthy();
  });
});
