import { describe, expect, it, vi } from "vitest";
import { resolve } from "node:path";
import { chromeKit } from "./extensionTestKit";

const extension = resolve(process.cwd(), "../chrome-extension");

describe("Chrome eklenti arka planı", () => {
  it("paneli açar, offscreen belgeyi kurar, komut/eşleşme iletilerini yönlendirir", async () => {
    const { chromeMock } = chromeKit();
    let actionClicked!: (tab: { id?: number }) => Promise<void>;
    let onMessage!: (m: Record<string, unknown>, s: object, r: (v: unknown) => void) => boolean;
    const sendNativeMessage = vi.fn(async () => ({ ok: true, port: 5000, anahtar: "t" }));
    const createDocument = vi.fn(async () => undefined);
    Object.assign(chromeMock, {
      action: { onClicked: { addListener: (l: typeof actionClicked) => { actionClicked = l; } } },
      sidePanel: { open: vi.fn(async () => undefined) },
      offscreen: { hasDocument: vi.fn(async () => false), createDocument },
      runtime: {
        onMessage: { addListener: (l: typeof onMessage) => { onMessage = l; } },
        onStartup: { addListener: vi.fn() },
        onInstalled: { addListener: vi.fn() },
        sendNativeMessage,
      },
    });
    vi.resetModules();
    await import("../../../chrome-extension/background.js");

    await actionClicked({ id: 7 });
    expect((chromeMock as unknown as { sidePanel: { open: ReturnType<typeof vi.fn> } }).sidePanel.open).toHaveBeenCalledWith({ tabId: 7 });
    await vi.waitFor(() => expect(createDocument).toHaveBeenCalled());

    const eslesme = vi.fn();
    expect(onMessage({ type: "fusion.pair" }, {}, eslesme)).toBe(true);
    await vi.waitFor(() => expect(eslesme).toHaveBeenCalledWith({ ok: true, port: 5000, anahtar: "t" }));
    expect(sendNativeMessage).toHaveBeenCalledWith("com.fusion.browser", { type: "pair" });

    const sonuc = vi.fn();
    expect(onMessage({ type: "fusion.exec", command: { islem: "tabs" } }, {}, sonuc)).toBe(true);
    await vi.waitFor(() => expect(sonuc.mock.calls[0][0].ok).toBe(true));

    const goruntu = vi.fn();
    onMessage({ type: "fusion.captureVisibleTab", windowId: 3 }, {}, goruntu);
    await vi.waitFor(() => expect(goruntu).toHaveBeenCalledWith({ ok: true, image: "data:image/jpeg;base64,abc" }));
  });
});
