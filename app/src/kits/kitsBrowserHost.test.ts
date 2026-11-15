import { describe, expect, it, vi } from "vitest";
import {
  KITS_BROWSER_DESCRIBE_RPC,
  KITS_BROWSER_RPC,
  KitsBrowserHost,
  READ_GRANT_TTL_MS,
  describeBrowserRequest,
  parseBrowserInput,
  parseKitIdentity,
} from "./kitsBrowserHost";

const ORIGIN = "http://127.0.0.1:4410";
const KOD = { id: "k1", name: "Kod" };

type Izin = boolean | ((summary: string, interactive: boolean, risky?: boolean) => boolean);
function fixture(izin: Izin = true, tarif: Record<string, unknown> = { ok: true, status: "ok", hedef: "", riskli: false }) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  const komut = vi.fn(async (_data: Record<string, unknown>) => ({ ok: true, status: "ok", text: '{"title":"Gelen kutusu"}' }));
  const request = vi.fn(async (name: string, data: Record<string, unknown>) =>
    name === KITS_BROWSER_DESCRIBE_RPC ? tarif : komut(data),
  );
  const confirm = vi.fn(async (summary: string, interactive: boolean, risky?: boolean) =>
    typeof izin === "function" ? izin(summary, interactive, risky) : izin,
  );
  let clock = 1_000;
  const client = new KitsBrowserHost(host, frame, `${ORIGIN}/?theme=dark`, request, confirm, () => clock);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  const replies = () => frame.postMessage.mock.calls.map((call) => call[0] as Record<string, unknown>);
  const komutlar = () => request.mock.calls.filter((call) => call[0] === KITS_BROWSER_RPC).map((call) => call[1]);
  const tick = (ms: number) => { clock += ms; };
  return { client, frame, request, komut, komutlar, confirm, send, replies, tick };
}
const req = (nonce: string, input: unknown, kit: unknown = KOD) => ({ type: "fusion-browser-request", nonce, input, kit });

describe("KitsBrowserHost", () => {
  it("okuma isteği Kit başına bir kez onaylanır; sonrakiler sorulmadan oturuma gider, sonuç aynı nonce ile döner", async () => {
    const f = fixture(true);
    f.send(req("n1", { action: "read", reason: "Gelen kutusunu oku" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.confirm).toHaveBeenCalledWith(expect.stringContaining("«Kod» Kit'i Chrome'unda açık sekmeyi okumak"), false, false);
    expect(f.request).toHaveBeenCalledWith(KITS_BROWSER_DESCRIBE_RPC, { action: "read" });
    expect(f.komutlar()).toEqual([{ action: "read" }]);
    expect(f.replies()[0]).toEqual({ type: "fusion-browser-result", nonce: "n1", status: "ok", text: '{"title":"Gelen kutusu"}' });
    f.send(req("n2", { action: "find", value: "Gönder" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(1);
    expect(f.komutlar()[1]).toEqual({ action: "find", value: "Gönder" });
  });

  it("okuma izni Kit'e ve gruba (sayfa / sekmeler) bağlıdır ve süresi dolunca yeniden sorulur", async () => {
    // Ölçüldü (31 Ekim): tek onay bütün Kit'lere, sekme listesine ve süresiz geçiyordu.
    const f = fixture(true);
    f.send(req("n1", { action: "read" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    f.send(req("n2", { action: "tabs" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(2);
    expect(f.confirm).toHaveBeenLastCalledWith(expect.stringContaining("açık sekmeleri listelemek"), false, false);
    f.send(req("n3", { action: "read" }, { id: "k2", name: "Pazarlama" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(3));
    expect(f.confirm).toHaveBeenCalledTimes(3);
    expect(f.confirm).toHaveBeenLastCalledWith(expect.stringContaining("«Pazarlama» Kit'i"), false, false);
    f.tick(READ_GRANT_TTL_MS + 1);
    f.send(req("n4", { action: "read" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(4));
    expect(f.confirm).toHaveBeenCalledTimes(4);
  });

  it("etkileşim eylemi her seferinde hedefiyle sorulur; ret oturuma hiç gitmez", async () => {
    let allow = true;
    const f = fixture((_summary, interactive) => (interactive ? allow : true), { ok: true, status: "ok", hedef: "Siparişi onayla", riskli: true });
    f.send(req("n1", { action: "click", ref: "e3" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.request).toHaveBeenCalledWith(KITS_BROWSER_DESCRIBE_RPC, { action: "click", ref: "e3" });
    expect(f.confirm).toHaveBeenLastCalledWith(
      expect.stringContaining("«Kod» Kit'i Chrome'unda «Siparişi onayla» öğesine tıklamak istiyor. DİKKAT"),
      true,
      true,
    );
    allow = false;
    f.send(req("n2", { action: "type", ref: "e3", value: "merhaba" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(2);
    expect(f.komutlar()).toHaveLength(1);
    expect(f.replies()[1]).toMatchObject({ nonce: "n2", status: "denied" });
  });

  it("tarif 'kapalı' ya da 'kullanılamaz' derse kullanıcıya hiç sorulmaz", async () => {
    const f = fixture(true, { ok: false, status: "denied", text: "Bu eylem kapalı: chrome_click aracı runtime.disabled_tools ile devre dışı." });
    f.send(req("n1", { action: "click", ref: "e3" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.confirm).not.toHaveBeenCalled();
    expect(f.komutlar()).toHaveLength(0);
    expect(f.replies()[0]).toMatchObject({ nonce: "n1", status: "denied", text: expect.stringContaining("chrome_click") });
  });

  it("başka kaynak/köken, geçersiz eylem ve ekran görüntüsü isteği reddedilir", async () => {
    const f = fixture(true);
    f.send(req("n1", { action: "read" }), "http://evil.test");
    f.send(req("n1", { action: "read" }), ORIGIN, {});
    f.send(req("n2", { action: "screenshot" }));
    f.send(req("n3", { action: "click", ref: 42 }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).not.toHaveBeenCalled();
    expect(f.request).not.toHaveBeenCalled();
    expect(f.replies().map((r) => [r.nonce, r.status])).toEqual([["n2", "failed"], ["n3", "failed"]]);
  });

  it("oturum yoksa kullanılamaz döner; sayfa metnindeki sırlar (sınırda kesilenler dahil) Kits'e gitmez", async () => {
    const f = fixture(true);
    f.komut.mockResolvedValueOnce({
      ok: true,
      status: "ok",
      text: "Terminal: export OPENAI_API_KEY=sk-proj-abcdefghijklmnop12\nFinder: /Users/ali/rapor.md",
    });
    f.send(req("n1", { action: "text" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    const text = String(f.replies()[0].text);
    expect(text).not.toContain("sk-proj");
    expect(text).toContain("/Users/ali/rapor.md");
    // Ölçüldü (31 Ekim): önce kesip sonra gizlemek sınırdaki yarım anahtarı sızdırıyordu.
    const dolgu = "x".repeat(20_000 - " sk-proj-abcd".length);
    f.komut.mockResolvedValueOnce({ ok: true, status: "ok", text: `${dolgu} sk-proj-abcdefghijklmnop1234567890` });
    f.send(req("n2", { action: "text" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(String(f.replies()[1].text)).not.toContain("sk-proj");
    f.request.mockRejectedValueOnce(new Error("Fusion oturumu yok."));
    f.send(req("n3", { action: "tabs" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(3));
    expect(f.replies()[2]).toMatchObject({ nonce: "n3", status: "unavailable" });
    expect(f.confirm).toHaveBeenCalledTimes(1);
  });

  it("istek özeti Kit'i, hedefi, yazılacak metni, tuşu ve gerekçeyi taşır; bilinmeyen alanlar atılır", () => {
    const input = parseBrowserInput({ action: "navigate", url: "https://ornek.com", reason: "Fiyat bak", extra: 1 });
    expect(input).toEqual({ action: "navigate", url: "https://ornek.com", reason: "Fiyat bak" });
    expect(describeBrowserRequest(input!)).toBe(
      "Kits Chrome'unda bir adrese gitmek (https://ornek.com) istiyor. Kit'in gerekçesi (Fusion doğrulamaz): Fiyat bak",
    );
    expect(describeBrowserRequest({ action: "click", ref: "e12" }, { kit: KOD })).toBe(
      "«Kod» Kit'i Chrome'unda adı okunamayan bir öğeye (e12) tıklamak istiyor.",
    );
    expect(describeBrowserRequest({ action: "type", ref: "e7", value: "parola: sk-proj-abcdefghijklmnop1234567890" }, { kit: KOD, target: "Arama" })).toBe(
      '«Kod» Kit\'i Chrome\'unda «Arama» alanına "parola: [gizlendi]" yazmak istiyor.',
    );
    expect(describeBrowserRequest({ action: "key" }, { kit: KOD, target: "Mesaj", risky: true })).toContain(
      "«Mesaj» alanında Enter tuşuna basmak istiyor. DİKKAT",
    );
    expect(describeBrowserRequest({ action: "key", value: "Escape" }, {})).toBe("Kits Chrome'unda Escape tuşuna basmak istiyor.");
    expect(parseKitIdentity({ id: "k1", name: "Kod\n\u0007" })).toEqual({ id: "k1", name: "Kod" });
    expect(parseKitIdentity({ id: "k1" })).toBeNull();
    expect(parseBrowserInput({ action: "read", value: "x".repeat(16_001) })).toBeNull();
    expect(parseBrowserInput(null)).toBeNull();
  });
});
