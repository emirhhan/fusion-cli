import { afterEach, expect, it, vi } from "vitest";
import { AssetHost } from "./assetHost";
afterEach(() => vi.useRealTimers());
function fixture(request: (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>> = vi.fn(async () => ({ ok: true, asset: { asset_id: "12345678-1234-4234-8234-123456789012", metadata_version: 1, available: true } }))) {
  const frame = { postMessage: vi.fn() };
  const bridge = new AssetHost(window, frame, "http://127.0.0.1:50003", request, 50);
  const emit = (origin = "http://127.0.0.1:50003", source: unknown = frame) => window.dispatchEvent(new MessageEvent("message", { origin, source: source as Window, data: { type: "fusion-asset-resolve", nonce: "nonce-1", asset_id: "12345678-1234-4234-8234-123456789012" } }));
  return { frame, bridge, request, emit };
}
it("yalnız aynı iframe ve origin isteğini çözer", async () => {
  const f = fixture();
  try {
    f.emit("https://wrong.example"); f.emit(undefined, {});
    expect(f.request).not.toHaveBeenCalled();
    f.emit();
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    expect(f.request).toHaveBeenCalledWith("artefakt.coz", { asset_id: "12345678-1234-4234-8234-123456789012" });
  } finally { f.bridge.close(); }
});
it("kapanış geç sonucu bastırır, aynı nonce eşzamanlı isteği çoğaltmaz", async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const request = vi.fn(() => new Promise<Record<string, unknown>>(resolve => { finish = resolve; }));
  const f = fixture(request);
  f.emit(); f.emit();
  expect(f.request).toHaveBeenCalledTimes(1);
  f.bridge.close(); finish({ ok: true, asset: {} });
  await Promise.resolve(); await Promise.resolve();
  expect(f.frame.postMessage).not.toHaveBeenCalled();
});
it("zaman aşımında belirsiz sonuç döner ve geç başarı kabul edilmez", async () => {
  vi.useFakeTimers();
  let finish!: (value: Record<string, unknown>) => void;
  const f = fixture(vi.fn(() => new Promise<Record<string, unknown>>(resolve => { finish = resolve; })));
  try {
    f.emit(); await vi.advanceTimersByTimeAsync(51);
    expect(f.frame.postMessage).toHaveBeenCalledWith(expect.objectContaining({ ok: false, nonce: "nonce-1" }), "http://127.0.0.1:50003");
    finish({ ok: true, asset: {} }); await Promise.resolve(); await Promise.resolve();
    expect(f.frame.postMessage).toHaveBeenCalledTimes(1);
  } finally { f.bridge.close(); }
});
it("yerel mutlak yolu ve bilinmeyen backend alanlarını iframe'e taşımaz", async () => {
  const f = fixture(vi.fn(async () => ({ ok: true, asset: { asset_id: "12345678-1234-4234-8234-123456789012", metadata_version: 1, available: true, path: "/private/gallery/image.png", future_private: "yerel değer" } })));
  try {
    f.emit();
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    const sent = f.frame.postMessage.mock.calls[0][0] as { asset: Record<string, unknown> };
    expect(sent.asset).not.toHaveProperty("path");
    expect(sent.asset).not.toHaveProperty("future_private");
    expect(sent.asset.asset_id).toBe("12345678-1234-4234-8234-123456789012");
  } finally { f.bridge.close(); }
});

it("bounded dosya sayfası yerel yolu taşımadan host üzerinden alınır", async () => {
  const id = "12345678-1234-4234-8234-123456789012";
  const request = vi.fn(async () => ({ ok: true, items: [{ asset_id: id, metadata_version: 1, available: true, path: "/private/image.png" }], next_cursor: null }));
  const f = fixture(request);
  try {
    window.dispatchEvent(new MessageEvent("message", { origin: "http://127.0.0.1:50003", source: f.frame as unknown as Window, data: { type: "fusion-asset-list", nonce: "page-1", cursor: null } }));
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith("artefakt.liste", { sinir: 50, cursor: null }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    const sent = f.frame.postMessage.mock.calls[0][0] as { items: Record<string, unknown>[] };
    expect(sent.items[0].asset_id).toBe(id);
    expect(sent.items[0]).not.toHaveProperty("path");
  } finally { f.bridge.close(); }
});

it("görsel önizlemesi kimlik ve sınırlı PNG dışında backend alanı taşımaz", async () => {
  const id = "12345678-1234-4234-8234-123456789012";
  const f = fixture(vi.fn(async () => ({ ok: true, asset_id: id, data_url: "data:image/png;base64,aGVsbG8=", width: 32, height: 32, sha256: "a".repeat(64), path: "/private/image.png" })));
  try {
    window.dispatchEvent(new MessageEvent("message", { origin: "http://127.0.0.1:50003", source: f.frame as unknown as Window, data: { type: "fusion-asset-preview", nonce: "preview-1", asset_id: id } }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));
    const sent = f.frame.postMessage.mock.calls[0][0];
    expect(sent).toMatchObject({ ok: true, asset_id: id, width: 32 });
    expect(sent).not.toHaveProperty("path");
  } finally { f.bridge.close(); }
});
