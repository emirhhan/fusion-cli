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
});
