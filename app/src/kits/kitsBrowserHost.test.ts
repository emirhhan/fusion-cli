import { describe, expect, it, vi } from "vitest";
import { KitsBrowserHost, describeBrowserRequest, parseBrowserInput } from "./kitsBrowserHost";

const ORIGIN = "http://127.0.0.1:4410";

function fixture(izin: boolean | ((summary: string, interactive: boolean) => boolean) = true) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  const request = vi.fn(async () => ({ ok: true, status: "ok", text: '{"title":"Gelen kutusu"}' }));
  const confirm = vi.fn(async (summary: string, interactive: boolean) =>
    typeof izin === "function" ? izin(summary, interactive) : izin,
  );
  const client = new KitsBrowserHost(host, frame, `${ORIGIN}/?theme=dark`, request, confirm);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  const replies = () => frame.postMessage.mock.calls.map((call) => call[0] as Record<string, unknown>);
  return { client, frame, request, confirm, send, replies };
}
const req = (nonce: string, input: unknown) => ({ type: "fusion-browser-request", nonce, input });

describe("KitsBrowserHost", () => {
  it("okuma isteği bir kez onaylanır, sonrakiler sorulmadan oturuma gider; sonuç aynı nonce ile döner", async () => {
    const f = fixture(true);
    f.send(req("n1", { action: "read", reason: "Gelen kutusunu oku" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.confirm).toHaveBeenCalledWith(expect.stringContaining("açık sekmeyi okumak"), false);
    expect(f.request).toHaveBeenCalledWith("chrome.kit_komut", { action: "read" });
    expect(f.replies()[0]).toEqual({ type: "fusion-browser-result", nonce: "n1", status: "ok", text: '{"title":"Gelen kutusu"}' });
    f.send(req("n2", { action: "find", value: "Gönder" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(1);
    expect(f.request).toHaveBeenLastCalledWith("chrome.kit_komut", { action: "find", value: "Gönder" });
  });

  it("etkileşim eylemi her seferinde sorulur; ret oturuma hiç gitmez", async () => {
    let allow = true;
    const f = fixture((_summary, interactive) => (interactive ? allow : true));
    f.send(req("n1", { action: "click", ref: "e3" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.confirm).toHaveBeenLastCalledWith(expect.stringContaining("tıklamak"), true);
    allow = false;
    f.send(req("n2", { action: "type", ref: "e3", value: "merhaba" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(2);
    expect(f.request).toHaveBeenCalledTimes(1);
    expect(f.replies()[1]).toMatchObject({ nonce: "n2", status: "denied" });
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

  it("oturum yoksa kullanılamaz döner; sayfa metnindeki sırlar Kits'e gitmez", async () => {
    const f = fixture(true);
    f.request.mockResolvedValueOnce({
      ok: true,
      status: "ok",
      text: "Terminal: export OPENAI_API_KEY=sk-proj-abcdefghijklmnop12\nFinder: /Users/ali/rapor.md",
    } as never);
    f.send(req("n1", { action: "text" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    const text = String(f.replies()[0].text);
    expect(text).not.toContain("sk-proj");
    expect(text).toContain("/Users/ali/rapor.md");
    f.request.mockRejectedValueOnce(new Error("Fusion oturumu yok."));
    f.send(req("n2", { action: "tabs" }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.replies()[1]).toMatchObject({ nonce: "n2", status: "unavailable" });
  });

  it("istek özeti hedef adresi ve Kit gerekçesini taşır; bilinmeyen alanlar atılır", () => {
    const input = parseBrowserInput({ action: "navigate", url: "https://ornek.com", reason: "Fiyat bak", extra: 1 });
    expect(input).toEqual({ action: "navigate", url: "https://ornek.com", reason: "Fiyat bak" });
    expect(describeBrowserRequest(input!)).toBe(
      "Kits Chrome'unda bir adrese gitmek (https://ornek.com) istiyor. Kit'in gerekçesi (Fusion doğrulamaz): Fiyat bak",
    );
    expect(parseBrowserInput({ action: "read", value: "x".repeat(16_001) })).toBeNull();
    expect(parseBrowserInput(null)).toBeNull();
  });
});
