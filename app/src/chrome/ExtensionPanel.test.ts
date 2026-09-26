import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromeKit } from "./extensionTestKit";

const extension = resolve(process.cwd(), "../chrome-extension");
const html = readFileSync(resolve(extension, "panel.html"), "utf8");

let calls: string[];
let kit: ReturnType<typeof chromeKit>;

async function loadPanel() {
  vi.resetModules();
  await import("../../../chrome-extension/panel.js");
}

beforeEach(() => {
  document.documentElement.innerHTML = html.match(/<body>([\s\S]*?)<\/body>/)?.[1] || "";
  calls = [];
  kit = chromeKit();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    calls.push(path);
    if (path === "/poll") return new Promise(() => undefined);
    const result = path === "/turn" ? { ok: true, metin: "Görev tamamlandı" } : {};
    return { ok: true, json: async () => result };
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

const click = (id: string) => fireEvent.click(document.getElementById(id)!);
const status = () => document.getElementById("status")?.textContent;

describe("Chrome eklenti paneli", () => {
  it("elle bağlanır, sekmeye izin verir, sayfayı okur, görev gönderir ve bağlantıyı keser", async () => {
    await loadPanel();
    (document.getElementById("port") as HTMLInputElement).value = "8765";
    (document.getElementById("token") as HTMLInputElement).value = "secret";
    click("connect");
    await waitFor(() => expect(status()).toBe("Bağlı"));

    click("select-tab");
    await waitFor(() => expect(document.getElementById("tab-label")?.textContent).toContain("example.com"));
    expect(kit.chromeMock.permissions.request).toHaveBeenCalledWith({ origins: ["https://example.com/*"] });

    click("read-tab");
    await waitFor(() => expect(document.getElementById("snapshot")?.textContent).toContain("Page text"));

    (document.getElementById("prompt") as HTMLTextAreaElement).value = "Özetle";
    click("send");
    await waitFor(() => expect(document.getElementById("response")?.textContent).toBe("Görev tamamlandı"));
    expect(calls).toContain("/turn");

    click("disconnect");
    await waitFor(() => expect(status()).toBe("Bağlı değil"));
    expect(kit.session.has("fusionTab")).toBe(false);
  });

  it("otomatik bağlıyken eşleştirme alanını gizler ve durumu gösterir", async () => {
    kit.session.set("fusionAuto", { bagli: true, port: 5000, token: "t" });
    await loadPanel();
    await waitFor(() => expect(status()).toBe("Otomatik bağlı"));
    expect(document.getElementById("pairing")?.hidden).toBe(true);
    (document.getElementById("prompt") as HTMLTextAreaElement).value = "Özetle";
    click("send");
    await waitFor(() => expect(calls).toContain("/turn"));
  });

  it("geçersiz eşleştirmeyi Fusion'a sormadan reddeder", async () => {
    await loadPanel();
    click("connect");
    await waitFor(() => expect(document.getElementById("error")?.textContent).toContain("portunu"));
    expect(calls).toEqual([]);
  });

  it("geniş ekran görüntüsü iznini yalnız düğmeyle ister", async () => {
    await loadPanel();
    expect(kit.chromeMock.permissions.request).not.toHaveBeenCalled();
    await kit.chromeMock.storage.session.set({ fusionAuto: { bagli: true, port: 5000, token: "t" } });
    await waitFor(() => expect(status()).toBe("Otomatik bağlı"));
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
