import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import type { SessionState } from "./types";
import { loadSessionView, saveSessionView, SESSION_VIEW_KEY } from "./persistence";

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } as Storage;
}

function state(): SessionState {
  const client = new ProtocolClient(() => undefined, () => undefined);
  return {
    activeId: "bir",
    order: ["bir"],
    connectionError: null,
    sessions: {
      bir: {
        id: "bir",
        title: "Oyun projesi",
        source: "claude",
        root: "/projeler/oyun",
        pid: 42,
        status: "ready",
        error: null,
        running: false,
        client,
        question: null,
        messages: [{ rol: "kullanici", metin: "TOKEN=çok-gizli-değer" }],
      },
    },
  };
}

describe("session persistence", () => {
  it("yalnız sürümlü güvenli metadata saklar", () => {
    const target = storage();
    saveSessionView(target, state(), 1234);

    const raw = target.getItem(SESSION_VIEW_KEY) ?? "";
    expect(raw).toContain('"version":1');
    expect(raw).toContain("Oyun projesi");
    expect(raw).not.toContain("çok-gizli-değer");
    expect(raw).not.toContain("messages");
    expect(raw).not.toContain("pid");
    expect(loadSessionView(target)?.sessions[0]).toEqual({
      id: "bir",
      title: "Oyun projesi",
      source: "claude",
      root: "/projeler/oyun",
      updatedAt: 1234,
    });
  });

  it("bozuk veya bilinmeyen sürümde güvenli boş dönüş yapar", () => {
    const target = storage();
    target.setItem(SESSION_VIEW_KEY, "bozuk-json");
    expect(loadSessionView(target)).toBeNull();
    target.setItem(SESSION_VIEW_KEY, JSON.stringify({ version: 99, sessions: [] }));
    expect(loadSessionView(target)).toBeNull();
  });
});
