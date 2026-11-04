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

// U4-08 (b) — Ölçüldü (29 Ekim): tur bitince SoruKapandi olayı kaybolursa soru kartı sonsuza
// kadar kalıyordu; yalnız crashed/cleared temizliyordu.
describe("tur bitince bekleyen soru", () => {
  const soru = (id: string) => ({ id, data: { tur: "soru", soru: id } as never });
  function bekleyenli() {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    state = sessionReducer(state, { type: "runningChanged", id: "bir", running: true });
    for (const id of ["q1", "q2"]) state = sessionReducer(state, { type: "questionChanged", id: "bir", question: soru(id) });
    return state;
  }
  it("running=false soru kartını ve kuyruğunu kapatır", () => {
    const state = sessionReducer(bekleyenli(), { type: "runningChanged", id: "bir", running: false });
    expect(state.sessions.bir.question).toBeNull();
    expect(state.sessions.bir.questionQueue).toEqual([]);
  });
  it("running=true soruya dokunmaz", () => {
    const state = sessionReducer(bekleyenli(), { type: "runningChanged", id: "bir", running: true });
    expect(state.sessions.bir.question?.id).toBe("q1");
    expect(state.sessions.bir.questionQueue).toHaveLength(1);
  });

  // Ölçüldü (30 Ekim): geçmiş gelmeden mesaj yazılırsa geri gelen geçmiş tamamen atılıyordu (U4-35);
  // iptal edilen turun akan metni sonraki model çağrısında sessizce siliniyordu (U5-11).
  it("geç gelen geçmiş, yazılmış mesajların önüne eklenir ve çift kullanıcı mesajı düşer (U4-35)", () => {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    state = sessionReducer(state, { type: "messageAdded", id: "bir", message: { id: "r1:user", rol: "kullanici", metin: "yeni soru" } });
    state = sessionReducer(state, {
      type: "historyLoaded", id: "bir",
      messages: [{ rol: "kullanici", metin: "eski" }, { rol: "asistan", metin: "eski cevap" }, { rol: "kullanici", metin: "yeni soru" }],
    });

    expect(state.sessions.bir.messages.map((m) => m.metin)).toEqual(["eski", "eski cevap", "yeni soru"]);
    expect(new Set(state.sessions.bir.messages.map((m) => m.id)).size).toBe(3);
  });

  it("tur son olaysız biterse akan metin kalıcı ara metne çevrilir (U5-11)", () => {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    state = sessionReducer(state, { type: "messageAdded", id: "bir", message: { id: "r1:user", rol: "kullanici", metin: "yaz" } });
    state = sessionReducer(state, { type: "runningChanged", id: "bir", running: true });
    state = sessionReducer(state, { type: "eventReceived", id: "bir", event: { olay: "TokenReceived", channel: "main", text: "yarım kalan cevap" } });
    state = sessionReducer(state, { type: "runningChanged", id: "bir", running: false });

    const son = state.sessions.bir.messages[state.sessions.bir.messages.length - 1];
    expect(son).toMatchObject({ rol: "asistan", metin: "yarım kalan cevap", ara: true });
    expect(son.akan).toBeUndefined();
  });

  it("nihai cevap zaten varsa akan balon kopya bırakmaz (U5-11)", () => {
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "bir", title: "Bir", source: "fusion", root: "/bir", client: client() },
    });
    state = sessionReducer(state, { type: "messageAdded", id: "bir", message: { id: "r1:user", rol: "kullanici", metin: "yaz" } });
    state = sessionReducer(state, { type: "eventReceived", id: "bir", event: { olay: "TokenReceived", channel: "main", text: "tam cevap" } });
    state = sessionReducer(state, { type: "messageAdded", id: "bir", message: { id: "r1:assistant", rol: "asistan", metin: "tam cevap" } });
    state = sessionReducer(state, { type: "runningChanged", id: "bir", running: false });

    expect(state.sessions.bir.messages.filter((m) => m.rol === "asistan")).toHaveLength(1);
  });
});


it("geç yaratılan geri yükleme kaydı seçili çalışan sohbeti değiştirmez", () => {
  let state = sessionReducer(initialSessionState, { type: "created", session: {
    id: "fresh", title: "Yeni iş", source: "fusion", root: "/project", client: client(),
  } });
  state = sessionReducer(state, { type: "runningChanged", id: "fresh", running: true });
  const owner = state.sessions.fresh;
  state = sessionReducer(state, { type: "created", activate: false, session: {
    id: "old", title: "Yeni görev", source: "fusion", root: "/outputs", client: client(),
  } });
  expect(state.activeId).toBe("fresh");
  expect(state.sessions.fresh).toBe(owner);
  expect(state.sessions.old.root).toBe("/outputs");
});

it("tekrarlanan created çalışan turun kökünü mesajını veya istemcisini ezemez", () => {
  let state = sessionReducer(initialSessionState, { type: "created", session: {
    id: "same", title: "Yeni iş", source: "fusion", root: "/project", client: client(),
  } });
  state = sessionReducer(state, { type: "submissionStarted", id: "same", requestId: "owner" });
  state = sessionReducer(state, { type: "messageAdded", id: "same", message: { rol: "kullanici", metin: "Hesabı temizle" } });
  state = sessionReducer(state, { type: "runningChanged", id: "same", running: true });
  const owner = state.sessions.same;
  state = sessionReducer(state, { type: "created", activate: false, session: {
    id: "same", title: "Yeni görev", source: "fusion", root: "/outputs", client: client(),
  } });
  expect(state.sessions.same).toBe(owner);
  expect(state.sessions.same.requestId).toBe("owner");
  expect(state.sessions.same.root).toBe("/project");
  expect(state.sessions.same.running).toBe(true);
  expect(state.sessions.same.messages[0].metin).toBe("Hesabı temizle");
});
