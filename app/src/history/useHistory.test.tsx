import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { useHistory } from "./useHistory";

function historyClient() {
  let receive: ((line: string) => void) | null = null;
  const client = new ProtocolClient(
    (line) => {
      const request = JSON.parse(line) as {
        id: string;
        ad: string;
        veri: Record<string, unknown>;
      };
      let veri: Record<string, unknown> = { ok: true };
      if (request.ad === "gecmis.kaynaklar") {
        veri = { ok: true, kaynaklar: [{ ad: "claude", komut: "/resumeclaude" }] };
      } else if (request.ad === "gecmis.oturumlar") {
        const cursor = Number(request.veri.cursor ?? 0);
        veri = {
          ok: true,
          kaynak: "claude",
          oturumlar: [{
            kaynak: "claude",
            oturum_id: cursor === 0 ? "c1" : "c2",
            baslik: cursor === 0 ? "Oyun" : "Site",
            guncellendi: 100 - cursor,
            tur_sayisi: 3,
            boyut: 120,
          }],
          next_cursor: cursor === 0 ? 1 : null,
          has_more: cursor === 0,
        };
      } else if (request.ad === "gecmis.ara") {
        const sorgu = String(request.veri.sorgu ?? "");
        veri = sorgu.trim()
          ? {
              ok: true,
              kaynak: "claude",
              oturumlar: [{
                kaynak: "claude",
                oturum_id: "eski",
                baslik: "2026-01-01 · 40 bayt",
                guncellendi: 5,
                tur_sayisi: 2,
                boyut: 40,
                baslikta: false,
                parca: `…${sorgu} loop kuruyorum`,
              }],
              taranan: 12,
              kismi: true,
              metin: "Tarama sınırına ulaşıldı.",
            }
          : { ok: false, metin: "Arama için en az bir karakter yazın." };
      } else if (request.ad === "gecmis.onizle") {
        const cursor = Number(request.veri.cursor ?? 0);
        veri = {
          ok: true,
          kaynak: "claude",
          oturum_id: request.veri.oturum_id,
          turlar: [{ rol: cursor === 0 ? "user" : "assistant", metin: `tur-${cursor}`, zaman: 10 }],
          next_cursor: cursor === 0 ? 1 : null,
          has_more: cursor === 0,
        };
      }
      queueMicrotask(() => receive?.(JSON.stringify({ tip: "sonuc", id: request.id, veri })));
    },
    (handler) => {
      receive = handler;
    },
  );
  return client;
}

describe("useHistory", () => {
  it("yalnız çekirdeğin keşfettiği kaynakları gösterir", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toEqual([
      { ad: "claude", komut: "/resumeclaude" },
    ]));
  });

  it("oturum ve önizleme sayfalarını aşamalı yükler", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    await act(async () => result.current.openSource("claude"));
    expect(result.current.sessions.map((session) => session.oturum_id)).toEqual(["c1"]);
    await act(async () => result.current.loadMoreSessions());
    expect(result.current.sessions.map((session) => session.oturum_id)).toEqual(["c1", "c2"]);

    await act(async () => result.current.selectSession(result.current.sessions[0]));
    expect(result.current.turns.map((turn) => turn.metin)).toEqual(["tur-0"]);
    await act(async () => result.current.loadMoreTurns());
    expect(result.current.turns.map((turn) => turn.metin)).toEqual(["tur-0", "tur-1"]);
  });

  it("arama sunucuya sorar ve yüklenmemiş oturumu da bulur", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    await act(async () => {
      await result.current.openSource("claude");
    });

    await act(async () => {
      await result.current.searchSessions("game");
    });

    expect(result.current.searchResults.map((s) => s.oturum_id)).toEqual(["eski"]);
    expect(result.current.searchResults[0].parca).toContain("game");
    expect(result.current.searchQuery).toBe("game");
  });

  it("kesilen aramayı kısmi olarak bildirir; sessizce sonuç yok demez", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    await act(async () => {
      await result.current.openSource("claude");
    });

    await act(async () => {
      await result.current.searchSessions("game");
    });

    expect(result.current.searchPartial).toBe(true);
    expect(result.current.searchNotice).toContain("Tarama");
  });

  it("arama temizlenince sayfalanmış listeye döner", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    await act(async () => {
      await result.current.openSource("claude");
    });
    await act(async () => {
      await result.current.searchSessions("game");
    });

    await act(async () => {
      await result.current.searchSessions("   ");
    });

    expect(result.current.searchQuery).toBe("");
    expect(result.current.searchResults).toEqual([]);
    expect(result.current.sessions).toHaveLength(1);
  });

  it("kaynak değişince önceki aramayı taşımaz", async () => {
    const client = historyClient();
    const { result } = renderHook(() => useHistory(client));
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    await act(async () => {
      await result.current.openSource("claude");
    });
    await act(async () => {
      await result.current.searchSessions("game");
    });

    await act(async () => {
      await result.current.openSource("claude");
    });

    expect(result.current.searchQuery).toBe("");
    expect(result.current.searchResults).toEqual([]);
  });
});
