import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { initialSessionState, sessionReducer } from "./store";

function session() {
  return sessionReducer(initialSessionState, { type: "created", session: {
    id: "bir", title: "Bir", source: "fusion", root: "/bir",
    client: new ProtocolClient(() => undefined, () => undefined),
  } });
}
const token = { olay: "TokenReceived", text: "merhaba", event_id: "attempt:1", session_id: "bir", turn_id: "tur", schema_version: 1 };

describe("Gönderim olay tekrarları", () => {
  it("aynı event_id token metnini iki kez eklemez", () => {
    const first = sessionReducer(session(), { type: "eventReceived", id: "bir", event: token });
    const replay = sessionReducer(first, { type: "eventReceived", id: "bir", event: token });
    expect(replay.sessions.bir.messages).toEqual(first.sessions.bir.messages);
    expect(replay.sessions.bir.messages[0].metin).toBe("merhaba");
  });

  it("başka session_id olayını hedef sohbetten ayıklar", () => {
    const initial = session();
    const next = sessionReducer(initial, { type: "eventReceived", id: "bir", event: { ...token, session_id: "iki" } });
    expect(next.sessions.bir.messages).toEqual([]);
  });
});

it("duplicate final outcome kapanış mesajını çoğaltmaz", () => {
  const event = { ...token, olay: "TurnOutcome", status: "completed", event_id: "attempt:final" };
  const first = sessionReducer(session(), { type: "eventReceived", id: "bir", event });
  const replay = sessionReducer(first, { type: "eventReceived", id: "bir", event });
  expect(replay.sessions.bir.messages).toEqual(first.sessions.bir.messages);
});

it("eski tur TokenReceived ve TurnFinished yeni turun metnini değiştirmez", () => {
  let current = sessionReducer(session(), { type: "eventReceived", id: "bir", event: { ...token, turn_id: "yeni" } });
  const before = current.sessions.bir.messages;
  current = sessionReducer(current, { type: "eventReceived", id: "bir", event: { ...token, event_id: "eski:2", turn_id: "eski" } });
  expect(current.sessions.bir.messages).toEqual(before);
  current = sessionReducer(current, { type: "eventReceived", id: "bir", event: { ...token, olay: "TurnFinished", event_id: "eski:3", turn_id: "eski" } });
  expect(current.sessions.bir.messages).toEqual(before);
});

it("duplicate TurnFinished replay state'i ikinci kez değiştirmez", () => {
  const event = { ...token, olay: "TurnFinished", event_id: "attempt:finished" };
  const first = sessionReducer(session(), { type: "eventReceived", id: "bir", event });
  const replay = sessionReducer(first, { type: "eventReceived", id: "bir", event });
  expect(replay.sessions.bir.messages).toEqual(first.sessions.bir.messages);
});

it("eski TurnFinished yeni turun akan cevabını silmez", () => {
  const current = sessionReducer(session(), { type: "eventReceived", id: "bir", event: { ...token, turn_id: "yeni" } });
  const next = sessionReducer(current, { type: "eventReceived", id: "bir", event: { ...token, olay: "TurnFinished", event_id: "eski:3", turn_id: "eski" } });
  expect(next.sessions.bir.messages).toEqual(current.sessions.bir.messages);
});

it("opak event_id araya başka olay girince de tekrar eklenmez", () => {
  const first = { ...token, event_id: "opaque-a", schema_version: undefined };
  const second = { ...token, event_id: "opaque-b", schema_version: undefined, text: " dünya" };
  let current = sessionReducer(session(), { type: "eventReceived", id: "bir", event: first });
  current = sessionReducer(current, { type: "eventReceived", id: "bir", event: second });
  const replay = sessionReducer(current, { type: "eventReceived", id: "bir", event: first });
  expect(replay.sessions.bir.messages).toEqual(current.sessions.bir.messages);
});

it("eski request makbuzu aktif request'in turunu değiştirmez", () => {
  const current = sessionReducer(session(), {type: "submissionStarted", id: "bir", requestId: "yeni"});
  const replay = sessionReducer(current, {type: "eventReceived", id: "bir", event: {olay: "GonderimMakbuzu", gonderim_id: "eski", turn_id: "eski:1"}});
  expect(replay).toBe(current);
});

it("yeni attempt eski sequence high-water'ını taşımaz", () => {
  let current = sessionReducer(session(), {type: "eventReceived", id: "bir", event: {...token, event_id: "eski:1:99", turn_id: "eski:1"}});
  current = sessionReducer(current, {type: "submissionStarted", id: "bir", requestId: "yeni"});
  current = sessionReducer(current, {type: "eventReceived", id: "bir", event: {olay: "GonderimMakbuzu", gonderim_id: "yeni", turn_id: "yeni:1"}});
  current = sessionReducer(current, {type: "eventReceived", id: "bir", event: {...token, event_id: "yeni:1:1", turn_id: "yeni:1", text: "yeni"}});
  expect(current.sessions.bir.eventSequence).toBe(1);
});

it("terminal opaque final son replay penceresinden çıktıktan sonra da upsert ile korunur", () => {
  const final = {...token, olay: "TurnOutcome", status: "completed", event_id: "opaque-final", schema_version: undefined};
  let current = sessionReducer(session(), {type: "eventReceived", id: "bir", event: final});
  for (let index = 0; index < 300; index++) current = sessionReducer(current, {type: "eventReceived", id: "bir", event: {...token, event_id: `opaque-${index}`, schema_version: undefined}});
  const replay = sessionReducer(current, {type: "eventReceived", id: "bir", event: final});
  expect(replay.sessions.bir.messages).toEqual(current.sessions.bir.messages);
  expect(current.sessions.bir.eventIds!.length).toBeLessThanOrEqual(256);
});

it("aynı request'in eski attempt makbuzu beklenen retry attempt'ini ele geçirmez", () => {
  const current = sessionReducer(session(), {type: "submissionStarted", id: "bir", requestId: "istek", expectedTurnId: "istek:2"});
  const old = sessionReducer(current, {type: "eventReceived", id: "bir", event: {olay: "GonderimMakbuzu", gonderim_id: "istek", turn_id: "istek:1"}});
  expect(old).toBe(current);
  const next = sessionReducer(current, {type: "eventReceived", id: "bir", event: {olay: "GonderimMakbuzu", gonderim_id: "istek", turn_id: "istek:2"}});
  expect(next.sessions.bir.turnId).toBe("istek:2");
});

it.each([undefined, "yeni:2"])("ilk makbuz öncesi eski token/final yeni attempt'i bağlamaz (%s)", (expectedTurnId) => {
  let current = sessionReducer(session(), { type: "submissionStarted", id: "bir", requestId: "yeni", expectedTurnId });
  for (const olay of ["TokenReceived", "TurnFinished", "TurnOutcome"]) {
    const next = sessionReducer(current, { type: "eventReceived", id: "bir", event: {
      ...token, olay, turn_id: "eski:1", event_id: "eski:1:99",
    } });
    expect(next).toBe(current);
  }
  current = sessionReducer(current, { type: "eventReceived", id: "bir", event: {
    olay: "GonderimMakbuzu", gonderim_id: "yeni", turn_id: expectedTurnId ?? "yeni:1", session_id: "bir",
  } });
  expect(current.sessions.bir.turnId).toBe(expectedTurnId ?? "yeni:1");
  expect(current.sessions.bir.eventSequence).toBeUndefined();
});
