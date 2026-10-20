import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useActiveModel } from "./useActiveModel";
import type { CatalogClient } from "./useModelCatalog";

test("A modelini B oturumunun pending veya reddedilen kontrolünde göstermez", async () => {
  const a: CatalogClient = { request: vi.fn(async () => ({ ok: true, model: { agent: "model-A" } })) };
  let finish!: (value: Record<string, unknown>) => void;
  const b: CatalogClient = { request: vi.fn(() => new Promise((resolve) => { finish = resolve; })) };
  const { result, rerender } = renderHook(({ client, id }) => useActiveModel(client, id, 0), { initialProps: { client: a, id: "A" } });
  await waitFor(() => expect(result.current.model).toBe("model-A"));
  rerender({ client: b, id: "B" });
  expect(result.current.model).toBe("");
  await act(async () => finish({ ok: false, metin: "reddedildi" }));
  expect(result.current.model).toBe("");
});

test("aynı oturum yenilemesinde son doğru model korunur ve eski sahip sonucu uygulanmaz", async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const a: CatalogClient = { request: vi.fn(() => new Promise((resolve) => { finish = resolve; })) };
  const b: CatalogClient = { request: vi.fn(async () => ({ ok: true, model: { agent: "model-B" } })) };
  const { result, rerender } = renderHook(({ client, id, revision }) => useActiveModel(client, id, revision), { initialProps: { client: a, id: "A", revision: 0 } });
  rerender({ client: b, id: "B", revision: 0 });
  await waitFor(() => expect(result.current.model).toBe("model-B"));
  await act(async () => finish({ ok: true, model: { agent: "late-A" } }));
  expect(result.current.model).toBe("model-B");
  b.request = vi.fn(async () => { throw new Error("yenileme reddi"); });
  rerender({ client: b, id: "B", revision: 1 });
  await act(async () => undefined);
  expect(result.current.model).toBe("model-B");
});
