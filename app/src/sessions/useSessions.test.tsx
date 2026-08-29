import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSessions } from "./useSessions";
import type { SessionClosedEvent, SessionLineEvent, SessionTransport } from "./types";

function fakeTransport() {
  let lineHandler: ((event: SessionLineEvent) => void) | null = null;
  let closedHandler: ((event: SessionClosedEvent) => void) | null = null;
  const sent: { id: string; line: string }[] = [];
  const unlistenLine = vi.fn();
  const unlistenClosed = vi.fn();
  const transport: SessionTransport = {
    create: vi.fn(async (id, root) => ({
      oturum_id: id,
      kok: root ?? "/aktif",
      pid: id === "varsayilan" ? 41 : 42,
      durum: "calisiyor",
      kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      sent.push({ id, line });
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => {
      lineHandler = handler;
      return unlistenLine;
    }),
    onClosed: vi.fn(async (handler) => {
      closedHandler = handler;
      return unlistenClosed;
    }),
  };
  return {
    transport,
    sent,
    emitLine: (event: SessionLineEvent) => lineHandler?.(event),
    emitClosed: (event: SessionClosedEvent) => closedHandler?.(event),
    unlistenLine,
    unlistenClosed,
  };
}

describe("useSessions", () => {
  it("her protokol satırını yalnız ait olduğu oturuma yönlendirir", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.id).toBe("varsayilan"));
    await act(async () => {
      await result.current.create({ id: "ikinci", title: "İkinci", root: "/ikinci" });
    });

    act(() => {
      result.current.send("varsayilan", "birinci görev");
      result.current.send("ikinci", "ikinci görev");
    });
    await waitFor(() => expect(fake.sent).toHaveLength(2));
    for (const item of fake.sent) {
      const request = JSON.parse(item.line) as { id: string };
      act(() => {
        fake.emitLine({
          oturum_id: item.id,
          satir: JSON.stringify({
            tip: "sonuc",
            id: request.id,
            veri: { metin: `${item.id} yanıtı` },
          }),
        });
      });
    }

    await waitFor(() => {
      expect(result.current.state.sessions.varsayilan.messages.at(-1)?.metin).toBe(
        "varsayilan yanıtı",
      );
      expect(result.current.state.sessions.ikinci.messages.at(-1)?.metin).toBe("ikinci yanıtı");
    });
  });

  it("yalnız kapanan oturumu çökmüş işaretler ve dinleyicileri temizler", async () => {
    const fake = fakeTransport();
    const { result, unmount } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    await act(async () => {
      await result.current.create({ id: "ikinci", title: "İkinci" });
    });

    act(() => fake.emitClosed({ oturum_id: "ikinci", neden: "çöktü" }));
    expect(result.current.state.sessions.ikinci.status).toBe("crashed");
    expect(result.current.state.sessions.varsayilan.status).toBe("ready");

    unmount();
    await waitFor(() => {
      expect(fake.unlistenLine).toHaveBeenCalledOnce();
      expect(fake.unlistenClosed).toHaveBeenCalledOnce();
    });
  });

  it("kullanıcının kapattığı oturumu çöküş olarak göstermez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    await act(async () => {
      await result.current.close("varsayilan");
    });
    act(() => fake.emitClosed({ oturum_id: "varsayilan", neden: "süreç kapandı" }));

    expect(result.current.state.sessions.varsayilan.status).toBe("closed");
    expect(result.current.state.sessions.varsayilan.error).toBeNull();
  });

  it("geçmiş künyesini yeni konuşmanın kendi çekirdeğinde hazırlar", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let resumePromise!: Promise<{ id: string; secretCount: number }>;
    act(() => {
      resumePromise = result.current.resume({
        source: "claude",
        sessionId: "claude-1",
        title: "Oyun konuşması",
      });
    });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const sent = fake.sent[0];
    const request = JSON.parse(sent.line) as { id: string; ad: string; veri: Record<string, string> };
    expect(sent.id).not.toBe("varsayilan");
    expect(request.ad).toBe("gecmis.surdur");
    expect(request.veri).toEqual({ kaynak: "claude", oturum_id: "claude-1" });

    act(() => {
      fake.emitLine({
        oturum_id: sent.id,
        satir: JSON.stringify({
          tip: "sonuc",
          id: request.id,
          veri: { ok: true, kaynak: "claude", baslik: "Oyun konuşması", sir_sayisi: 2 },
        }),
      });
    });
    await act(async () => {
      await expect(resumePromise).resolves.toEqual({ id: sent.id, secretCount: 2 });
    });
    expect(result.current.state.sessions[sent.id].source).toBe("claude");
    expect(result.current.state.sessions[sent.id].title).toBe("[claude] Oyun konuşması");
  });
});
