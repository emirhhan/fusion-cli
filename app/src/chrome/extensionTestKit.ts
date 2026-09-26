import { vi } from "vitest";

/** Eklenti testleri için durumlu, en küçük Chrome API taklidi. */
export function chromeKit(options: { granted?: (origin: string) => boolean } = {}) {
  const session = new Map<string, unknown>();
  const listeners: ((changes: Record<string, unknown>, area: string) => void)[] = [];
  const tabs = [
    { id: 7, url: "https://example.com/page", title: "Example", active: true, status: "complete", windowId: 1 },
    { id: 8, url: "https://ads.google.com/aw/campaigns", title: "Google Ads", active: false, status: "complete", windowId: 1 },
  ];
  const granted = options.granted ?? (() => true);
  const chromeMock = {
    storage: {
      session: {
        get: vi.fn(async (key: string | string[]) => {
          const keys = Array.isArray(key) ? key : [key];
          return Object.fromEntries(keys.filter((k) => session.has(k)).map((k) => [k, session.get(k)]));
        }),
        set: vi.fn(async (values: Record<string, unknown>) => {
          for (const [k, v] of Object.entries(values)) session.set(k, v);
          listeners.forEach((l) => l(Object.fromEntries(Object.keys(values).map((k) => [k, {}])), "session"));
        }),
        remove: vi.fn(async (key: string) => { session.delete(key); listeners.forEach((l) => l({ [key]: {} }, "session")); }),
      },
      onChanged: { addListener: (l: (typeof listeners)[number]) => listeners.push(l) },
    },
    tabs: {
      query: vi.fn(async (q: { active?: boolean }) => (q.active ? tabs.filter((t) => t.active) : tabs)),
      get: vi.fn(async (id: number) => {
        const tab = tabs.find((t) => t.id === id);
        if (!tab) throw new Error("No tab");
        return tab;
      }),
      update: vi.fn(async (id: number, props: { url?: string; active?: boolean }) => {
        const tab = tabs.find((t) => t.id === id)!;
        Object.assign(tab, props);
        return tab;
      }),
      create: vi.fn(async (props: { url: string }) => {
        const tab = { id: 9, url: props.url, title: "Yeni", active: true, status: "complete", windowId: 1 };
        tabs.push(tab);
        return tab;
      }),
      onUpdated: { addListener: vi.fn(), removeListener: vi.fn() },
      captureVisibleTab: vi.fn(async () => "data:image/jpeg;base64,abc"),
    },
    permissions: {
      request: vi.fn(async () => true),
      contains: vi.fn(async ({ origins }: { origins: string[] }) => origins.every((o) => granted(o))),
    },
    scripting: {
      executeScript: vi.fn(async () => [{ result: { title: "Example", url: "https://example.com/page", text: "Page text", elements: [] } }]),
    },
  };
  vi.stubGlobal("chrome", chromeMock);
  return { chromeMock, session, tabs };
}
