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
});
