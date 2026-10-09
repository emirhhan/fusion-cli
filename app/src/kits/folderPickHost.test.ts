import { describe, expect, it, vi } from "vitest";
import { FolderPickHost } from "./folderPickHost";

const ORIGIN = "http://127.0.0.1:4410";

function fixture(secim: string | null = "/Users/me/oyun") {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  const pick = vi.fn(async () => secim);
  const client = new FolderPickHost(host, frame, `${ORIGIN}/?theme=dark`, pick);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  return { client, frame, pick, send };
}

describe("FolderPickHost", () => {
  it("seçilen klasörü aynı nonce ile yalnız Kits kökenine döner", async () => {
    const f = fixture();
    f.send({ type: "fusion-folder-request", nonce: "n1" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalled());
    expect(f.frame.postMessage).toHaveBeenCalledWith(
      { type: "fusion-folder-result", nonce: "n1", path: "/Users/me/oyun" },
      ORIGIN,
    );
  });
  it("vazgeçilen seçim boş yol döner", async () => {
    const f = fixture(null);
    f.send({ type: "fusion-folder-request", nonce: "n2" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalled());
    expect(f.frame.postMessage.mock.calls[0][0]).toMatchObject({ path: null });
  });
  it("yabancı köken, kaynak ya da bozuk istek seçici açmaz", () => {
    const f = fixture();
    f.send({ type: "fusion-folder-request", nonce: "n" }, "http://evil.test");
    f.send({ type: "fusion-folder-request", nonce: "n" }, ORIGIN, {});
    f.send({ type: "fusion-folder-request" });
    f.client.close();
    f.send({ type: "fusion-folder-request", nonce: "n" });
    expect(f.pick).not.toHaveBeenCalled();
  });
});
