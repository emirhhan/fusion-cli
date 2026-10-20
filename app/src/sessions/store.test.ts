import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { initialSessionState, sessionReducer } from "./store";

function client() {
  return new ProtocolClient(() => undefined, () => undefined);
}

describe("sessionReducer", () => {
  it("Chrome panelinden cevaplanan soru kartını yalnız kimlik eşleşirse kapatır", () => {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    const soru = { id: "5", data: { tur: "onay", arac: "chrome_click" } as never };
    state = sessionReducer(state, { type: "questionChanged", id: "bir", question: soru });
    state = sessionReducer(state, { type: "questionClosed", id: "bir", questionId: "4" });
    expect(state.sessions.bir.question?.id).toBe("5");
    state = sessionReducer(state, { type: "questionClosed", id: "bir", questionId: "5" });
    expect(state.sessions.bir.question).toBeNull();
  });

  it("oturumları oluşturur, seçer ve başlığını günceller", () => {
    const first = client();
    const second = client();
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Yeni görev", source: "fusion", root: "/bir", client: first },
    });
    state = sessionReducer(state, {
      type: "created",
      session: { id: "iki", title: "İkinci", source: "fusion", root: "/iki", client: second },
    });
    state = sessionReducer(state, { type: "selected", id: "bir" });
    state = sessionReducer(state, { type: "titleChanged", id: "bir", title: "Oyun projesi" });

    expect(state.activeId).toBe("bir");
    expect(state.sessions.bir.title).toBe("Oyun projesi");
    expect(state.sessions.bir.client).toBe(first);
    expect(state.sessions.iki.client).toBe(second);
  });

  it("her oturumun mesaj ve çalışma durumunu birbirinden ayırır", () => {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    state = sessionReducer(state, {
      type: "created",
      session: { id: "iki", title: "İki", source: "fusion", root: "/iki", client: client() },
    });
    state = sessionReducer(state, {
      type: "messageAdded",
      id: "bir",
      message: { rol: "kullanici", metin: "oyun yap" },
    });
    state = sessionReducer(state, { type: "runningChanged", id: "bir", running: true });
    state = sessionReducer(state, { type: "crashed", id: "iki", reason: "süreç kapandı" });

    expect(state.sessions.bir.messages).toEqual([{ id: expect.any(String), rol: "kullanici", metin: "oyun yap" }]);
    expect(state.sessions.bir.running).toBe(true);
    expect(state.sessions.bir.status).toBe("ready");
    expect(state.sessions.iki.messages).toEqual([]);
    expect(state.sessions.iki.status).toBe("crashed");
    expect(state.sessions.iki.error).toBe("süreç kapandı");
  });
});

it.each(["cleared", "crashed"] as const)("%s eski soru kuyruğunu da temizler", (type) => {
  let state = sessionReducer(initialSessionState, { type: "created", session: { id: "one", title: "Bir", source: "fusion", root: "/one", client: client() } });
  for (const id of ["q1", "q2"]) state = sessionReducer(state, { type: "questionChanged", id: "one", question: { id, data: { tur: "soru", soru: id } } });
  state = sessionReducer(state, type === "cleared" ? { type, id: "one" } : { type, id: "one", reason: "offline" });
  state = sessionReducer(state, { type: "questionChanged", id: "one", question: { id: "q3", data: { tur: "soru", soru: "Yeni" } } });
  state = sessionReducer(state, { type: "questionClosed", id: "one", questionId: "q3" });
  expect(state.sessions.one.question).toBeNull();
  expect(state.sessions.one.questionQueue).toEqual([]);
});
it("yalnız gerçek gönderim başlangıcı eski açık ajanları kapatır, steer/kuyruk mesajı kapatmaz", () => {
 let state = sessionReducer(initialSessionState, { type: "created", session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() } });
 state = sessionReducer(state, { type: "eventReceived", id: "bir", event: { olay: "SubAgentStarted", sub_id: "a", title: "Uzman", task: "Oku" } });
 for (const text of ["Yönlendirme", "Sıradaki iş"]) {
  state = sessionReducer(state, { type: "messageAdded", id: "bir", message: { rol: "kullanici", metin: text } });
  expect(state.sessions.bir.messages.flatMap(m => m.ajanlar ?? [])[0].durum).toBe("calisiyor");
 }
 state = sessionReducer(state, { type: "submissionStarted", id: "bir", requestId: "yeni" });
 expect(state.sessions.bir.messages.flatMap(m => m.ajanlar ?? [])[0].durum).toBe("yarim");
});

it("metinsiz biten ses isteğinin kimliğini sonraki görev çalışırken korur", () => {
  let state = sessionReducer(initialSessionState, {type: "created", session: {id: "voice", title: "Ses", source: "fusion", root: "/", client: client()}});
  state = sessionReducer(state, {type: "submissionStarted", id: "voice", requestId: "first"});
  state = sessionReducer(state, {type: "submissionCompleted", id: "voice", requestId: "first"});
  state = sessionReducer(state, {type: "submissionStarted", id: "voice", requestId: "second"});
  expect(state.sessions.voice.completedRequestIds).toEqual(["first"]);
  expect(state.sessions.voice.messages).toEqual([]);
  for (let index = 0; index < 110; index++) state = sessionReducer(state, {type: "submissionCompleted", id: "voice", requestId: String(index)});
  expect(state.sessions.voice.completedRequestIds).toHaveLength(100);
});
