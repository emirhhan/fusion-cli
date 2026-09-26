import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const extension = resolve(process.cwd(), "../chrome-extension");
const html = readFileSync(resolve(extension, "panel.html"), "utf8");
const script = readFileSync(resolve(extension, "panel.js"), "utf8");

type ChromeMock = {
  storage: { session: { get: ReturnType<typeof vi.fn>; set: ReturnType<typeof vi.fn>; clear: ReturnType<typeof vi.fn> } };
  tabs: { query: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> };
  permissions: { request: ReturnType<typeof vi.fn>; contains: ReturnType<typeof vi.fn> };
  scripting: { executeScript: ReturnType<typeof vi.fn> };
};

let chromeMock: ChromeMock;
let calls: string[];

beforeEach(async () => {
  document.documentElement.innerHTML = html.match(/<body>([\s\S]*?)<\/body>/)?.[1] || "";
  calls = [];
  chromeMock = {
    storage: { session: {
      get: vi.fn().mockResolvedValue({}), set: vi.fn().mockResolvedValue(undefined),
      clear: vi.fn().mockResolvedValue(undefined),
    } },
    tabs: {
      query: vi.fn().mockResolvedValue([{ id: 7, url: "https://example.com/page", title: "Example" }]),
      get: vi.fn().mockResolvedValue({ id: 7, url: "https://example.com/page" }),
    },
    permissions: {
      request: vi.fn().mockResolvedValue(true), contains: vi.fn().mockResolvedValue(true),
    },
    scripting: { executeScript: vi.fn().mockResolvedValue([{ result: {
      title: "Example", url: "https://example.com/page", text: "Page text", elements: [],
    } }]) },
  };
  vi.stubGlobal("chrome", chromeMock);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    calls.push(path);
    if (path === "/poll") return new Promise(() => undefined);
    const result = path === "/turn" ? { ok: true, metin: "Görev tamamlandı" } : {};
    return { ok: true, json: async () => result };
  }));
  await new (Object.getPrototypeOf(async function () {}).constructor)(script)();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("Chrome extension panel buttons", () => {
  it("connects, grants tab access, reads the page, sends a prompt, and disconnects", async () => {
    const click = (id: string) => fireEvent.click(document.getElementById(id)!);
    (document.getElementById("port") as HTMLInputElement).value = "8765";
    (document.getElementById("token") as HTMLInputElement).value = "secret";
    click("connect");
    await waitFor(() => expect(document.getElementById("status")?.textContent).toBe("Bağlı"));
    expect(chromeMock.storage.session.set).toHaveBeenCalledWith({ fusionConnection: { port: 8765, token: "secret" } });

    click("select-tab");
    await waitFor(() => expect(document.getElementById("tab-label")?.textContent).toContain("Example"));
    expect(chromeMock.permissions.request).toHaveBeenCalledWith({ origins: ["https://example.com/*"] });

    click("read-tab");
    await waitFor(() => expect(document.getElementById("snapshot")?.textContent).toContain("Page text"));
    expect(chromeMock.scripting.executeScript).toHaveBeenCalled();

    (document.getElementById("prompt") as HTMLTextAreaElement).value = "Özetle";
    click("send");
    await waitFor(() => expect(document.getElementById("response")?.textContent).toBe("Görev tamamlandı"));
    expect((document.getElementById("prompt") as HTMLTextAreaElement).value).toBe("");
    expect(calls).toContain("/turn");

    click("disconnect");
    await waitFor(() => expect(document.getElementById("status")?.textContent).toBe("Bağlı değil"));
    expect(chromeMock.storage.session.clear).toHaveBeenCalled();
  });

  it("rejects invalid pairing details before contacting Fusion", async () => {
    fireEvent.click(document.getElementById("connect")!);
    await waitFor(() => expect(document.getElementById("error")?.textContent).toContain("portunu"));
    expect(calls).toEqual([]);
  });

  it("requests broad capture permission only after its button is clicked", async () => {
    (document.getElementById("port") as HTMLInputElement).value = "8765";
    (document.getElementById("token") as HTMLInputElement).value = "secret";
    fireEvent.click(document.getElementById("connect")!);
    await waitFor(() => expect(document.getElementById("status")?.textContent).toBe("Bağlı"));
    expect(chromeMock.permissions.request).not.toHaveBeenCalled();
    fireEvent.click(document.querySelector("#capture-permission summary")!);
    fireEvent.click(document.getElementById("grant-capture")!);
    await waitFor(() => expect(chromeMock.permissions.request).toHaveBeenCalledWith({ origins: ["<all_urls>"] }));
  });

  it("running task exposes a working stop control", async () => {
    let resolveTurn!: (value: { ok: boolean; json: () => Promise<unknown> }) => void;
    const pendingTurn = new Promise<{ ok: boolean; json: () => Promise<unknown> }>((resolve) => { resolveTurn = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = new URL(url).pathname;
      calls.push(path);
      if (path === "/poll") return new Promise(() => undefined);
      if (path === "/turn") return pendingTurn;
      return { ok: true, json: async () => path === "/cancel" ? { ok: true, metin: "Durduruldu" } : {} };
    }));
    (document.getElementById("port") as HTMLInputElement).value = "8765";
    (document.getElementById("token") as HTMLInputElement).value = "secret";
    fireEvent.click(document.getElementById("connect")!);
    await waitFor(() => expect(document.getElementById("status")?.textContent).toBe("Bağlı"));
    fireEvent.click(document.getElementById("select-tab")!);
    await waitFor(() => expect(document.getElementById("tab-label")?.textContent).toContain("Example"));
    (document.getElementById("prompt") as HTMLTextAreaElement).value = "Uzun görev";
    fireEvent.click(document.getElementById("send")!);
    await waitFor(() => expect(document.getElementById("cancel")?.hidden).toBe(false));
    fireEvent.click(document.getElementById("cancel")!);
    await waitFor(() => expect(calls).toContain("/cancel"));
    resolveTurn({ ok: true, json: async () => ({ ok: false, metin: "Durduruldu" }) });
    await waitFor(() => expect(document.getElementById("cancel")?.hidden).toBe(true));
  });
});
