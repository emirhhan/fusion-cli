import { describe, expect, it, vi } from "vitest";
import { LocalComputerHost } from "./localComputerHost";

const ORIGIN = "http://127.0.0.1:4410";

function fixture(izin = true) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  const request = vi.fn(async () => ({
    ok: true, status: "observed", snapshot_id: "s:1", text: "Uygulama: Finder", images: ["data:x"],
  }));
  const confirm = vi.fn(async () => izin);
  const client = new LocalComputerHost(host, frame, `${ORIGIN}/?theme=dark`, request, confirm);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  return { client, frame, request, confirm, send };
}

describe("LocalComputerHost", () => {
  it("izin verilince oturumdan gözlem alır ve aynı nonce ile Kits'e döner", async () => {
    const f = fixture(true);
    f.send({ type: "fusion-computer-request", nonce: "n1", reason: "Finder'da ne açık?" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalled());
    expect(f.confirm).toHaveBeenCalledWith("Finder'da ne açık?");
    expect(f.request).toHaveBeenCalledWith("bilgisayar.snapshot", {});
    expect(f.frame.postMessage).toHaveBeenCalledWith(
      { type: "fusion-computer-result", nonce: "n1", status: "observed", snapshotId: "s:1", text: "Uygulama: Finder" },
      ORIGIN,
    );
  });

  it("kullanıcı reddederse oturuma hiç gitmez", async () => {
    const f = fixture(false);
    f.send({ type: "fusion-computer-request", nonce: "n2", reason: "bak" });
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalled());
    expect(f.request).not.toHaveBeenCalled();
    expect(f.frame.postMessage.mock.calls[0][0]).toMatchObject({ nonce: "n2", status: "denied" });
  });

  it("başka kaynaktan ya da kökenden gelen isteği yok sayar", async () => {
    const f = fixture(true);
    f.send({ type: "fusion-computer-request", nonce: "n3", reason: "x" }, "http://evil.test");
    f.send({ type: "fusion-computer-request", nonce: "n3", reason: "x" }, ORIGIN, {});
    await new Promise((r) => setTimeout(r, 10));
    expect(f.confirm).not.toHaveBeenCalled();
    expect(f.frame.postMessage).not.toHaveBeenCalled();
  });
});
