import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { initialSessionState, sessionReducer } from "./store";
import type { OlayAdimi } from "../protocol/olayMetni";

const sessionId = "calculator";
const turnId = "request:1";
const started = (callId: string, extra: Partial<OlayAdimi> = {}): OlayAdimi => ({
  arac: "view_image", metin: "Ekran inceleniyor", basladi: true,
  callId, sessionId, turnId, attemptId: turnId, ...extra,
});
function running(steps: OlayAdimi[]) {
  let state = sessionReducer(initialSessionState, { type: "created", session: {
    id: sessionId, title: "Hesap", source: "fusion", root: "/test",
    client: new ProtocolClient(() => undefined, () => undefined),
  } });
  state = sessionReducer(state, { type: "submissionStarted", id: sessionId, requestId: "request" });
  state = sessionReducer(state, { type: "messageAdded", id: sessionId,
    message: { id: "request:user", rol: "kullanici", metin: "37 ile 16'yı çarp" } });
  state = sessionReducer(state, { type: "eventReceived", id: sessionId,
    event: { olay: "GonderimMakbuzu", gonderim_id: "request", session_id: sessionId, turn_id: turnId } });
  state = sessionReducer(state, { type: "runningChanged", id: sessionId, running: true });
  return sessionReducer(state, { type: "messageAdded", id: sessionId,
    message: { rol: "olay", metin: "İşlemler", baslangicZamani: 10, adimlar: steps } });
}
const stepsOf = (state: ReturnType<typeof running>) => state.sessions[sessionId].messages.flatMap(message => message.adimlar ?? []);

describe("terminal turn without tool receipt", () => {
  it("closes the actual cancelled trace shape without claiming tool success or cancellation", () => {
    let state = running([started("pending"), started("done", { basladi: false, durum: "failed", cikti: "Gerçek hata" })]);
    state = sessionReducer(state, { type: "messageAdded", id: sessionId,
      message: { rol: "asistan", metin: "Tur iptal edildi." } });
    const stopped = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(stepsOf(stopped)[0]).toMatchObject({ basladi: false, durum: "unknown" });
    expect(stepsOf(stopped)[0].cikti).toContain("sonucu alınamadı");
    expect(stepsOf(stopped)[1]).toEqual(stepsOf(state)[1]);
    expect(stopped.sessions[sessionId].messages.find(message => message.rol === "olay")?.bitisZamani).toEqual(expect.any(Number));
    expect(sessionReducer(stopped, { type: "runningChanged", id: sessionId, running: false }).sessions[sessionId].messages)
      .toEqual(stopped.sessions[sessionId].messages);
  });

  it("does not close another session, turn or attempt in the same activity block", () => {
    const state = running([started("owned"), started("session", { sessionId: "foreign" }),
      started("turn", { turnId: "other:1", attemptId: "other:1" }), started("attempt", { attemptId: "request:2" })]);
    const stopped = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(stepsOf(stopped)[0]).toMatchObject({ basladi: false, durum: "unknown" });
    expect(stepsOf(stopped).slice(1)).toEqual(stepsOf(state).slice(1));
  });

  it("closes the owned turn even when a queued user message follows it", () => {
    let state = running([started("pending")]);
    state = sessionReducer(state, { type: "messageAdded", id: sessionId,
      message: { id: "queued:user", rol: "kullanici", metin: "Sonra bunu yap" } });
    const stopped = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(stepsOf(stopped)[0]).toMatchObject({ basladi: false, durum: "unknown" });
  });

  it("does not finalize a tool just because Stop was requested or failed", () => {
    const state = running([started("pending")]);
    const requested = sessionReducer(state, { type: "stopRequested", id: sessionId });
    expect(stepsOf(requested)).toEqual(stepsOf(state));
    expect(stepsOf(sessionReducer(requested, { type: "stopFailed", id: sessionId, error: "Bekliyor" }))).toEqual(stepsOf(state));
  });

  it("replays ToolStarted, cancelled answer, and terminal RPC state, then accepts a late real receipt", () => {
    let state = running([]);
    state = sessionReducer(state, { type: "eventReceived", id: sessionId, event: {
      olay: "ToolStarted", name: "view_image", args: { path: "screen.png" }, metin: "Ekran inceleniyor",
      session_id: sessionId, turn_id: turnId, attempt_id: turnId, call_id: "late", event_id: "started",
    } });
    state = sessionReducer(state, { type: "messageAdded", id: sessionId,
      message: { rol: "asistan", metin: "Tur iptal edildi." } });
    state = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(stepsOf(state)).toHaveLength(1);
    expect(stepsOf(state)[0]).toMatchObject({ basladi: false, durum: "unknown" });
    state = sessionReducer(state, { type: "eventReceived", id: sessionId, event: {
      olay: "ToolExecuted", name: "view_image", args: { path: "screen.png" }, outcome: "failed", output: "Gerçek araç sonucu",
      session_id: sessionId, turn_id: turnId, attempt_id: turnId, call_id: "late", event_id: "finished",
    } });
    expect(stepsOf(state)).toHaveLength(1);
    expect(stepsOf(state)[0]).toMatchObject({ basladi: false, durum: "failed", cikti: "Gerçek araç sonucu" });
  });

  it("limits legacy calls without wire ownership to the current user turn", () => {
    let state = running([started("new", { sessionId: undefined, turnId: undefined, attemptId: undefined })]);
    const before = state.sessions[sessionId];
    state = { ...state, sessions: { ...state.sessions, [sessionId]: { ...before, messages: [
      { rol: "olay", metin: "Eski", adimlar: [started("old", { sessionId: undefined, turnId: undefined, attemptId: undefined })] },
      ...before.messages,
    ] } } };
    const stopped = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(stepsOf(stopped)[0]).toEqual(stepsOf(state)[0]);
    expect(stepsOf(stopped)[1]).toMatchObject({ basladi: false, durum: "unknown" });
  });

  it("does not change another running session or revive a finalized call in the next turn", () => {
    let state = running([started("pending")]);
    state = sessionReducer(state, { type: "created", session: { id: "other", title: "Diğer", source: "fusion", root: "/other",
      client: new ProtocolClient(() => undefined, () => undefined) } });
    state = sessionReducer(state, { type: "runningChanged", id: "other", running: true });
    const other = state.sessions.other;
    state = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    expect(state.sessions.other).toBe(other);
    const stopped = stepsOf(state);
    state = sessionReducer(state, { type: "submissionStarted", id: sessionId, requestId: "next" });
    state = sessionReducer(state, { type: "runningChanged", id: sessionId, running: true });
    expect(stepsOf(state)).toEqual(stopped);
  });

  it("replaces an exactly owned uncertain result even after a queued user message", () => {
    let state = running([started("queued-late")]);
    state = sessionReducer(state, { type: "messageAdded", id: sessionId,
      message: { id: "queued:user", rol: "kullanici", metin: "Sonraki görev" } });
    state = sessionReducer(state, { type: "runningChanged", id: sessionId, running: false });
    state = sessionReducer(state, { type: "eventReceived", id: sessionId, event: {
      olay: "ToolExecuted", name: "view_image", outcome: "failed", output: "Gerçek geç sonuç",
      session_id: sessionId, turn_id: turnId, attempt_id: turnId, call_id: "queued-late",
    } });
    expect(stepsOf(state)).toHaveLength(1);
    expect(stepsOf(state)[0]).toMatchObject({ durum: "failed", cikti: "Gerçek geç sonuç" });
    expect(stepsOf(state)[0].sonucAlinamadi).toBeUndefined();
  });
});
