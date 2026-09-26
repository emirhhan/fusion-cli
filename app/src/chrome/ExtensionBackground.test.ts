import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const script = readFileSync(resolve(process.cwd(), "../chrome-extension/background.js"), "utf8");

describe("Chrome extension background", () => {
  it("opens the clicked tab panel and forwards a visible screenshot", async () => {
    let actionClicked!: (tab: { id?: number }) => Promise<void>;
    let onMessage!: (message: { type: string; windowId: number }, sender: object, reply: (value: unknown) => void) => boolean | undefined;
    const open = vi.fn().mockResolvedValue(undefined);
    const captureVisibleTab = vi.fn().mockResolvedValue("data:image/jpeg;base64,abc");
    const chromeMock = {
      action: { onClicked: { addListener: (listener: typeof actionClicked) => { actionClicked = listener; } } },
      sidePanel: { open },
      runtime: { onMessage: { addListener: (listener: typeof onMessage) => { onMessage = listener; } } },
      tabs: { captureVisibleTab },
    };
    Function("chrome", script)(chromeMock);

    await actionClicked({ id: 7 });
    expect(open).toHaveBeenCalledWith({ tabId: 7 });
    const reply = vi.fn();
    expect(onMessage({ type: "fusion.captureVisibleTab", windowId: 3 }, {}, reply)).toBe(true);
    await vi.waitFor(() => expect(reply).toHaveBeenCalledWith({ ok: true, image: "data:image/jpeg;base64,abc" }));
    expect(captureVisibleTab).toHaveBeenCalledWith(3, { format: "jpeg", quality: 65 });
  });
});
