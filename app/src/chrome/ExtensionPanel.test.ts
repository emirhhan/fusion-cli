import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromeKit } from "./extensionTestKit";

const extension = resolve(process.cwd(), "../chrome-extension");
const html = readFileSync(resolve(extension, "panel.html"), "utf8");

let calls: { path: string; body: Record<string, unknown> }[];
let kit: ReturnType<typeof chromeKit>;
/** Sırayla dönecek `/events` cevapları; boşken uzun yoklama yenisini bekler. */
let eventQueue: Record<string, unknown>[];
let eventWaiter: ((value: Record<string, unknown>) => void) | null;
const pushEvents = (value: Record<string, unknown>) => {
  if (eventWaiter) { eventWaiter(value); eventWaiter = null; } else eventQueue.push(value);
};
let turnResult: Promise<Record<string, unknown>>;

async function loadPanel() {
  vi.resetModules();
  await import("../../../chrome-extension/panel.js");
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

beforeEach(() => {
  document.documentElement.innerHTML = html.match(/<body>([\s\S]*?)<\/body>/)?.[1] || "";
  calls = [];
  eventQueue = [];
  eventWaiter = null;
  turnResult = Promise.resolve({ ok: true, metin: "Görev **tamamlandı**" });
  kit = chromeKit();
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { body?: string }) => {
    const path = new URL(url).pathname;
    calls.push({ path, body: init?.body ? JSON.parse(init.body) : {} });
    if (path === "/poll") return new Promise(() => undefined);
    if (path === "/events") {
      const next = eventQueue.shift() ?? await new Promise<Record<string, unknown>>((r) => { eventWaiter = r; });
      return { ok: true, json: async () => next };
    }
    const result = path === "/turn" ? await turnResult : path === "/status" ? { son: 3 } : { ok: true };
    return { ok: true, json: async () => result };
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

const $ = (id: string) => document.getElementById(id)!;
const click = (id: string) => fireEvent.click($(id));
const status = () => $("status").textContent;
const paths = () => calls.map((call) => call.path);
const send = (text: string) => {
  ($("prompt") as HTMLTextAreaElement).value = text;
  fireEvent.submit($("composer"));
};
const autoConnected = () => kit.session.set("fusionAuto", { bagli: true, port: 5000, token: "t" });

describe("Chrome eklenti paneli (Claude in Chrome gibi sohbet)", () => {
  it("elle bağlanır, görevi gönderir, cevabı sohbet olarak gösterir ve bağlantıyı keser", async () => {
    await loadPanel();
    ($("port") as HTMLInputElement).value = "8765";
    ($("token") as HTMLInputElement).value = "secret";
    click("connect");
    await waitFor(() => expect(status()).toBe("Bağlı"));

    send("Özetle");
    await waitFor(() => expect($("messages").textContent).toContain("Görev tamamlandı"));
    expect($("messages").querySelector(".bubble")?.textContent).toBe("Özetle");
    expect($("messages").querySelector("strong")?.textContent).toBe("tamamlandı");
    expect(calls.find((call) => call.path === "/turn")?.body).toEqual({ prompt: "Özetle" });
    expect($("empty").hidden).toBe(true);

    click("disconnect");
    await waitFor(() => expect(status()).toBe("Bağlı değil"));
    expect(kit.session.has("fusionTab")).toBe(false);
  });

  it("adımları canlı gösterir; izin kartını panelde cevaplar", async () => {
    const tur = deferred<Record<string, unknown>>();
    turnResult = tur.promise;
    const olaylar = { ok: true, son: 5, olaylar: [
        { seq: 4, tur: "adim", arac: "chrome_action", metin: "Sayfa aşağı kaydırıldı", durum: "ok" },
        { seq: 5, tur: "soru", id: "9", veri: { tur: "onay", baslik: "Tarayıcıda bu işlem yapılsın mı?", hedef: "“Paylaş”",
          secenekler: [{ deger: "once", etiket: "Evet" }, { deger: "deny", etiket: "Hayır" }] } },
    ] };
    autoConnected();
    await loadPanel();
    await waitFor(() => expect(status()).toBe("Bağlı"));
    expect($("pairing").hidden).toBe(true);
    send("Kaydır ve paylaş");
    await waitFor(() => expect($("cancel").hidden).toBe(false));
    pushEvents(olaylar);
    await waitFor(() => expect($("ask").hidden).toBe(false));
    expect($("messages").textContent).toContain("Sayfa aşağı kaydırıldı");
    expect($("send").hidden).toBe(true);
    expect($("cancel").hidden).toBe(false);
    expect($("ask").textContent).toContain("“Paylaş”");

    fireEvent.keyDown($("ask"), { key: "1" });
    await waitFor(() => expect(paths()).toContain("/answer"));
    expect(calls.find((call) => call.path === "/answer")?.body).toEqual({ id: "9", veri: { secim: "once" } });
    expect($("ask").hidden).toBe(true);

    tur.resolve({ ok: true, metin: "Paylaşıldı" });
    await waitFor(() => expect($("messages").textContent).toContain("Paylaşıldı"));
    expect($("send").hidden).toBe(false);
  });

  it("Durdur düğmesi turu keser; ilk açılışta eski turlar oynatılmaz", async () => {
    turnResult = new Promise(() => undefined);
    autoConnected();
    await loadPanel();
    await waitFor(() => expect(calls.find((call) => call.path === "/events")?.body).toEqual({ after: 3 }));
    send("Uzun iş");
    await waitFor(() => expect($("cancel").hidden).toBe(false));
    click("cancel");
    await waitFor(() => expect(paths()).toContain("/cancel"));
    await waitFor(() => expect($("messages").textContent).toContain("Durduruldu."));
  });

  it("model metnindeki HTML'i çalıştırmaz, düz metin gösterir", async () => {
    turnResult = Promise.resolve({ ok: true, metin: "<img src=x onerror=alert(1)> merhaba" });
    autoConnected();
    await loadPanel();
    send("Dene");
    await waitFor(() => expect($("messages").textContent).toContain("merhaba"));
    expect($("messages").querySelector("img")).toBeNull();
    expect($("messages").textContent).toContain("<img src=x");
  });

  it("öneri çipi görevi gönderir; izinsiz sitede izin düğmesi çıkar", async () => {
    kit = chromeKit({ granted: () => false });
    autoConnected();
    await loadPanel();
    await waitFor(() => expect($("select-tab").hidden).toBe(false));
    expect($("tab-label").textContent).toBe("example.com");
    click("select-tab");
    await waitFor(() => expect(kit.chromeMock.permissions.request).toHaveBeenCalledWith({ origins: ["https://example.com/*"] }));
    fireEvent.click(document.querySelector(".suggestion")!);
    await waitFor(() => expect(calls.find((call) => call.path === "/turn")?.body).toEqual({ prompt: "Bu sayfayı kısaca özetle." }));
  });

  it("arka plan eski sürümde kaldıysa tek tıkla kendini güncelleyen düğme gösterir", async () => {
    kit = chromeKit({ backgroundVersion: null });
    const reload = vi.fn();
    (kit.chromeMock.runtime as Record<string, unknown>).reload = reload;
    await loadPanel();
    await waitFor(() => expect($("update").hidden).toBe(false));
    click("reload-extension");
    expect(reload).toHaveBeenCalled();
  });

  it("arka plan güncelse güncelleme bandı gizli kalır", async () => {
    await loadPanel();
    await waitFor(() => expect(kit.chromeMock.runtime.sendMessage).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect($("update").hidden).toBe(true);
  });

  it("geçersiz eşleştirmeyi Fusion'a sormadan reddeder", async () => {
    await loadPanel();
    click("connect");
    await waitFor(() => expect($("error").textContent).toContain("portunu"));
    expect(calls).toEqual([]);
  });

  it("geniş ekran görüntüsü iznini yalnız düğmeyle ister", async () => {
    await loadPanel();
    expect(kit.chromeMock.permissions.request).not.toHaveBeenCalled();
    click("grant-capture");
    await waitFor(() => expect(kit.chromeMock.permissions.request).toHaveBeenCalledWith({ origins: ["<all_urls>"] }));
  });
});

describe("Çekirdek: sekme yönetimi", () => {
  it("sekmeleri listeler, izinli siteye yeni sekme açıp bağlar", async () => {
    vi.resetModules();
    const core = await import("../../../chrome-extension/core.js");
    const liste = await core.execute({ islem: "tabs" });
    expect(liste.tabs.map((t: { id: number }) => t.id)).toEqual([7, 8]);
    const acilan = await core.execute({ islem: "tab_open", veri: { url: "https://www.instagram.com/moto.gate/" } });
    expect(acilan.opened).toBe(9);
    expect((await core.getSelected()).origin).toBe("https://www.instagram.com");
  });

  it("izin verilmeyen siteye sekme açmaz", async () => {
    kit = chromeKit({ granted: (o) => !o.includes("evil") });
    vi.resetModules();
    const core = await import("../../../chrome-extension/core.js");
    await expect(core.execute({ islem: "tab_open", veri: { url: "https://evil.test/" } })).rejects.toThrow("izni yok");
  });

  it("seçili sekme yoksa izinli etkin sekmeye kendisi bağlanır", async () => {
    vi.resetModules();
    const core = await import("../../../chrome-extension/core.js");
    const sonuc = await core.execute({ islem: "snapshot", veri: {} });
    expect(sonuc.title).toBe("Example");
    expect((await core.getSelected()).id).toBe(7);
  });
});

describe("Sayfa içi eylemler (pageAction)", () => {
  let action: (op: string, args?: Record<string, unknown>) => Record<string, unknown>;

  beforeEach(async () => {
    vi.resetModules();
    const core = await import("../../../chrome-extension/core.js");
    action = (op, args = {}) => core.pageAction(op, args);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      { width: 100, height: 20, top: 10, bottom: 30, left: 0, right: 100, x: 0, y: 10, toJSON: () => ({}) } as DOMRect,
    );
    HTMLElement.prototype.scrollIntoView = vi.fn();
    (globalThis as { __fusionRefs?: unknown }).__fusionRefs = undefined;
    document.body.innerHTML = `
      <button aria-label="Kampanyalar">K</button>
      <input id="ara" placeholder="Ara" />
      <input type="password" name="password" />
      <select id="donem"><option value="7">Son 7 gün</option><option value="30">Son 30 gün</option></select>`;
  });

  it("metinle öğe bulur; parola alanını hiç göstermez", () => {
    expect(JSON.stringify(action("snapshot"))).not.toContain("password");
    const bulunan = action("find", { query: "kampanya" }) as { matches: { name: string }[] };
    expect(bulunan.matches[0].name).toBe("Kampanyalar");
  });

  it("React kontrollü alana yerel ayarlayıcıyla yazar ve input olayı yayar", () => {
    const giris = document.getElementById("ara") as HTMLInputElement;
    const olaylar: string[] = [];
    giris.addEventListener("input", () => olaylar.push(giris.value));
    const { matches } = action("find", { query: "ara" }) as { matches: { ref: string }[] };
    action("type", { ref: matches[0].ref, text: "motogate" });
    expect(olaylar).toEqual(["motogate"]);
  });

  it("tıklamadan önce düğmenin adını ve gönderme düğmesi olup olmadığını söyler", () => {
    document.body.insertAdjacentHTML("beforeend", "<form><button>Paylaş</button></form>");
    const { matches } = action("find", { query: "paylaş" }) as { matches: { ref: string }[] };
    expect(action("describe", { ref: matches[0].ref })).toMatchObject({ name: "Paylaş", submit: true });
  });

  it("gerçek adrese giden bağlantıyı '#' ve javascript: bağlantısından ayırır", () => {
    document.body.insertAdjacentHTML("beforeend",
      '<a href="/p/123">Gönderi 1.234 beğenme</a><a href="#">Gönderiyi sil</a><a href="javascript:void(0)">Gönderi arşivle</a>');
    const { matches } = action("find", { query: "gönderi" }) as { matches: { ref: string }[] };
    expect(matches.map((m) => action("describe", { ref: m.ref }).link)).toEqual([true, false, false]);
  });

  it("seçim kutusunda metinle seçer ve Enter gönderir", () => {
    const secim = document.getElementById("donem") as HTMLSelectElement;
    const { matches } = action("find", { query: "son 7" }) as { matches: { ref: string; tag: string }[] };
    action("select", { ref: matches.find((m) => m.tag === "select")!.ref, value: "30 gün" });
    expect(secim.value).toBe("30");
    const tuslar: string[] = [];
    document.body.addEventListener("keydown", (event) => tuslar.push(event.key));
    action("key", { key: "Enter" });
    expect(tuslar).toEqual(["Enter"]);
  });
});
