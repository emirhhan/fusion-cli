import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { initialSessionState, sessionReducer } from "./store";

function client() {
  return new ProtocolClient(() => undefined, () => undefined);
}

describe("sessionReducer", () => {
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

    expect(state.sessions.bir.messages).toEqual([{ rol: "kullanici", metin: "oyun yap" }]);
    expect(state.sessions.bir.running).toBe(true);
    expect(state.sessions.bir.status).toBe("ready");
    expect(state.sessions.iki.messages).toEqual([]);
    expect(state.sessions.iki.status).toBe("crashed");
    expect(state.sessions.iki.error).toBe("süreç kapandı");
  });
});
