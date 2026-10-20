import { describe, expect, it, vi } from "vitest";
import { KitsVoiceHost, VOICE_EVENT, VOICE_REQUEST, VOICE_RESULT } from "./kitsVoiceHost";
import type { DictationRuntime } from "../voice/useDictation";

const ORIGIN = "http://127.0.0.1:4410";

function fixture() {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  let lineHandler: Parameters<DictationRuntime["onLine"]>[0] = () => {};
  let endedHandler: Parameters<DictationRuntime["onEnded"]>[0] = () => {};
  const runtime: DictationRuntime = {
    onLine: vi.fn(async (handler) => { lineHandler = handler; return () => { lineHandler = () => {}; }; }),
    onEnded: vi.fn(async (handler) => { endedHandler = handler; return () => { endedHandler = () => {}; }; }),
    start: vi.fn(async () => 7),
    stop: vi.fn(async () => undefined),
  };
  const request = vi.fn(async (name: string) => {
    if (name === "ses.konus") return { ok: true, tur_id: "t1" };
    return { ok: true, tamamlandi: true };
  });
  const voice = new KitsVoiceHost(host, frame, `${ORIGIN}/?surface=kits`, request, runtime);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  const line = (session: number, value: object) => lineHandler({ session, line: JSON.stringify(value) });
  const ended = (session: number, message?: string) =>
    endedHandler({ session, stderr_summary: message ? { message } : null });
  return { voice, frame, runtime, request, send, line, ended };
}
const result = (nonce: string, ok = true) =>
  expect.objectContaining({ type: VOICE_RESULT, nonce, ok });

describe("KitsVoiceHost", () => {
  it("hello'ya yalnız Kits kökeninden ve bu iframe'den cevap verir", async () => {
    const f = fixture();
    f.send({ type: VOICE_REQUEST, nonce: "x", action: "hello" }, "http://evil.example");
    f.send({ type: VOICE_REQUEST, nonce: "y", action: "hello" }, ORIGIN, {});
    f.send({ type: VOICE_REQUEST, nonce: "z", action: "kod-calistir" });
    f.send({ type: VOICE_REQUEST, nonce: "n1", action: "hello" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.frame.postMessage).toHaveBeenCalledWith(result("n1"), ORIGIN);
  });

  it("dinlerken tanınan kısmi ve son sözleri Kits'e iletir; başka oturumun satırını yok sayar", async () => {
    const f = fixture();
    f.send({ type: VOICE_REQUEST, nonce: "l1", action: "listen" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledWith(result("l1"), ORIGIN));
    f.line(7, { tur: "kismi", metin: "merha" });
    f.line(3, { tur: "son", metin: "eski oturum" });
    f.line(7, { tur: "son", metin: "merhaba Kit" });
    expect(f.frame.postMessage).toHaveBeenCalledWith({ type: VOICE_EVENT, event: "partial", text: "merha" }, ORIGIN);
    expect(f.frame.postMessage).toHaveBeenCalledWith({ type: VOICE_EVENT, event: "final", text: "merhaba Kit" }, ORIGIN);
    expect(f.frame.postMessage).not.toHaveBeenCalledWith(expect.objectContaining({ text: "eski oturum" }), ORIGIN);
    f.send({ type: VOICE_REQUEST, nonce: "l2", action: "stop-listening" });
    await vi.waitFor(() => expect(f.runtime.stop).toHaveBeenCalled());
  });

  it("tanıma beklenmedik biçimde biterse Türkçe hata olayı gönderir", async () => {
    const f = fixture();
    f.send({ type: VOICE_REQUEST, nonce: "l1", action: "listen" });
    await vi.waitFor(() => expect(f.runtime.start).toHaveBeenCalled());
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledWith(result("l1"), ORIGIN));
    f.ended(7);
    expect(f.frame.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: VOICE_EVENT, event: "error", text: expect.stringContaining("izin") }), ORIGIN,
    );
  });

  it("seslendirme ses.konus ile başlar, ses.bekle bitince cevap verir", async () => {
    const f = fixture();
    f.send({ type: VOICE_REQUEST, nonce: "s1", action: "speak", text: "Merhaba, buradayım." });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledWith(result("s1"), ORIGIN));
    expect(f.request).toHaveBeenNthCalledWith(1, "ses.konus", { metin: "Merhaba, buradayım." });
    expect(f.request).toHaveBeenNthCalledWith(2, "ses.bekle", { tur_id: "t1" });
  });

  it("konuşma sürerken durdurma isteği aynı turu ses.durdur ile keser", async () => {
    const f = fixture();
    let finish: (value: Record<string, unknown>) => void = () => {};
    f.request.mockImplementation(async (name: string) => {
      if (name === "ses.konus") return { ok: true, tur_id: "t9" };
      if (name === "ses.bekle") return new Promise((resolve) => { finish = resolve; });
      return { ok: true };
    });
    f.send({ type: VOICE_REQUEST, nonce: "s1", action: "speak", text: "Uzun bir cevap." });
    await vi.waitFor(() => expect(f.request).toHaveBeenCalledWith("ses.bekle", { tur_id: "t9" }));
    f.send({ type: VOICE_REQUEST, nonce: "s2", action: "stop-speaking" });
    await vi.waitFor(() => expect(f.request).toHaveBeenCalledWith("ses.durdur", { tur_id: "t9" }));
    finish({ ok: true, tamamlandi: false });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledWith(result("s1"), ORIGIN));
  });

  it("Fusion oturumu seslendiremezse hatayı Kits'e iletir", async () => {
    const f = fixture();
    f.request.mockResolvedValueOnce({ ok: false, metin: "Ses kapalı." });
    f.send({ type: VOICE_REQUEST, nonce: "s1", action: "speak", text: "Deneme." });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledWith(
      { type: VOICE_RESULT, nonce: "s1", ok: false, error: "Ses kapalı." }, ORIGIN,
    ));
  });

  it("kapanınca dinlemeyi bırakır ve yeni istekleri yok sayar", async () => {
    const f = fixture();
    f.send({ type: VOICE_REQUEST, nonce: "l1", action: "listen" });
    await vi.waitFor(() => expect(f.runtime.start).toHaveBeenCalled());
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalled());
    f.voice.close();
    await vi.waitFor(() => expect(f.runtime.stop).toHaveBeenCalled());
    f.frame.postMessage.mockClear();
    f.send({ type: VOICE_REQUEST, nonce: "n2", action: "hello" });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(f.frame.postMessage).not.toHaveBeenCalled();
  });
});
