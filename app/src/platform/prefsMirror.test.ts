import { describe, expect, it, vi } from "vitest";
import { hydratePrefs, installPrefsMirror, isMirroredKey } from "./prefsMirror";

function fakeStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get length() { return values.size; },
    key: (index: number) => [...values.keys()][index] ?? null,
    getItem: (key: string) => values.get(key) ?? null,
    setItem(key: string, value: string) { values.set(key, value); },
    removeItem(key: string) { values.delete(key); },
    clear() { values.clear(); },
  };
}
const client = (degerler: Record<string, string>, ok = true) => ({
  request: vi.fn(async (name: string) => name === "ayar.arayuz" ? { ok, degerler, metin: "hata" } : { ok: true }),
});

describe("arayüz tercihi yedeği", () => {
  it("yalnız izinli anahtarları yedekler; taslak ve ekler dışarıda", () => {
    expect(isMirroredKey("fusion.layout")).toBe(true);
    expect(isMirroredKey("fusion.sidebar.history-open.v1")).toBe(true);
    expect(isMirroredKey("fusion.projects.v1")).toBe(true);
    expect(isMirroredKey("fusion.submissions.abc")).toBe(false);
    expect(isMirroredKey("baska")).toBe(false);
  });

  it("boş yerel depoyu çekirdekten doldurur ve yenileme gerektiğini söyler", async () => {
    const storage = fakeStorage();
    const changed = await hydratePrefs(client({ "fusion.layout": "{\"a\":1}", "fusion.submissions.x": "gizli" }), storage);
    expect(changed).toBe(true);
    expect(storage.getItem("fusion.layout")).toBe("{\"a\":1}");
    expect(storage.getItem("fusion.submissions.x")).toBeNull();
  });

  it("değerler zaten aynıysa yenileme istemez", async () => {
    const storage = fakeStorage({ "fusion.layout": "1" });
    expect(await hydratePrefs(client({ "fusion.layout": "1" }), storage)).toBe(false);
  });

  it("çekirdekte olmayan yerel tercihi çekirdeğe taşır", async () => {
    const storage = fakeStorage({ "fusion.sidebar.history-open.v1": "false", "fusion.submissions.x": "t" });
    const c = client({});
    expect(await hydratePrefs(c, storage)).toBe(false);
    expect(c.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.sidebar.history-open.v1", deger: "false" });
    expect(c.request).not.toHaveBeenCalledWith("ayar.arayuz_kaydet", expect.objectContaining({ anahtar: "fusion.submissions.x" }));
  });

  it("çekirdek hata verirse hata fırlatır", async () => {
    await expect(hydratePrefs(client({}, false), fakeStorage())).rejects.toThrow("hata");
  });

  it("yazma ve silmeyi çekirdeğe iletir, yamayı geri alır", async () => {
    const proto = fakeStorage();
    const c = client({});
    const restore = installPrefsMirror(c, vi.fn(), proto as unknown as Storage);
    proto.setItem("fusion.layout", "x");
    proto.setItem("fusion.submissions.y", "taslak");
    proto.removeItem("fusion.layout");
    expect(c.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.layout", deger: "x" });
    expect(c.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.layout", deger: null });
    expect(c.request).toHaveBeenCalledTimes(2);
    restore();
    proto.setItem("fusion.layout", "z");
    expect(c.request).toHaveBeenCalledTimes(2);
  });

  it("çekirdek kaydetmezse hatayı bildirir", async () => {
    const proto = fakeStorage();
    const onError = vi.fn();
    installPrefsMirror({ request: async () => ({ ok: false, metin: "disk dolu" }) }, onError, proto as unknown as Storage);
    proto.setItem("fusion.layout", "x");
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("disk dolu"));
  });

  // Ölçüldü (29 Ekim): yama `try { orijinal } finally { gönder }` idi; kota/SecurityError ile
  // yazma başarısız olsa da değer çekirdeğe gidiyor, yerel ve çekirdek ayrışıyordu.
  it("yerel yazma başarısızsa değer çekirdeğe gönderilmez; hata çağırana iletilir", () => {
    const proto = fakeStorage();
    proto.setItem = () => { throw new DOMException("kota", "QuotaExceededError"); };
    const c = client({});
    installPrefsMirror(c, vi.fn(), proto as unknown as Storage);
    expect(() => proto.setItem("fusion.layout", "x")).toThrow("kota");
    expect(c.request).not.toHaveBeenCalled();
  });

  it("yalnız asıl depoyu yedekler; başka depo örneğinin yazımı çekirdeğe gitmez", () => {
    const proto = fakeStorage();
    const asil = {};
    const c = client({});
    installPrefsMirror(c, vi.fn(), proto as unknown as Storage, asil);
    proto.setItem("fusion.layout", "x");
    expect(c.request).not.toHaveBeenCalled();
    proto.setItem.call(asil, "fusion.layout", "y");
    expect(c.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.layout", deger: "y" });
  });

  it("clear() izinli anahtarları çekirdekten de siler", () => {
    const proto = fakeStorage({ "fusion.layout": "1", "fusion.submissions.x": "t" });
    const c = client({});
    installPrefsMirror(c, vi.fn(), proto as unknown as Storage);
    (proto as unknown as Storage).clear();
    expect(c.request).toHaveBeenCalledWith("ayar.arayuz_kaydet", { anahtar: "fusion.layout", deger: null });
    expect(c.request).toHaveBeenCalledTimes(1);
  });

  it("hydrate: yerel yazma hatası kalan anahtarları atlatmaz ve hata fırlatmaz", async () => {
    const storage = fakeStorage();
    const ham = storage.setItem.bind(storage);
    storage.setItem = (key: string, value: string) => {
      if (key === "fusion.layout") throw new Error("kota");
      ham(key, value);
    };
    const changed = await hydratePrefs(client({ "fusion.layout": "1", "fusion.theme": "dark" }), storage);
    expect(changed).toBe(true);
    expect(storage.getItem("fusion.theme")).toBe("dark");
  });

  it("hydrate: çekirdeğe taşıma isteği reddedilirse yakalanmamış hata doğmaz", async () => {
    const storage = fakeStorage({ "fusion.theme": "light" });
    const reddeden = {
      request: vi.fn(async (name: string) => {
        if (name === "ayar.arayuz") return { ok: true, degerler: {} };
        throw new Error("kapandı");
      }),
    };
    const yakalanmayan = vi.fn();
    process.on("unhandledRejection", yakalanmayan);
    await hydratePrefs(reddeden, storage);
    await new Promise((cozumle) => setTimeout(cozumle, 20));
    process.off("unhandledRejection", yakalanmayan);
    expect(yakalanmayan).not.toHaveBeenCalled();
  });
});
