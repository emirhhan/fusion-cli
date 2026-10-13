import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useModelCatalog, type CatalogClient } from "./useModelCatalog";
function deferred() {
  let resolve!: (payload: Record<string, unknown>) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Record<string, unknown>>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const payload = (model: string) => ({ ok: true, modeller: [{ model, kaynak: "nim-free" }] });

test("stale session result cannot replace a new session catalog", async () => {
  const a = deferred(), b = deferred();
  const first: CatalogClient = { request: vi.fn(() => a.promise) };
  const second: CatalogClient = { request: vi.fn(() => b.promise) };
  const { result, rerender } = renderHook(({ client, id }) => useModelCatalog(client, id, "kod"), { initialProps: { client: first, id: "a" } });
  let loadA!: Promise<void>, loadB!: Promise<void>;
  act(() => { loadA = result.current.load(); });
  rerender({ client: second, id: "b" });
  act(() => { loadB = result.current.load(); });
  await act(async () => { b.resolve(payload("B")); await loadB; });
  await act(async () => { a.resolve(payload("A")); await loadA; });
  expect(result.current.options.map((x) => x.modelId)).toEqual(["B"]);
});

test("older rejection cannot turn the newest catalog into an error", async () => {
  const old = deferred(), fresh = deferred();
  const client = { request: vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise) };
  const { result } = renderHook(() => useModelCatalog(client, "a", "kod"));
  let one!: Promise<void>, two!: Promise<void>;
  act(() => { one = result.current.load(); two = result.current.load(); });
  await act(async () => { fresh.resolve(payload("B")); await two; });
  await act(async () => { old.reject(new Error("stale")); await one; });
  expect(result.current.state.status).toBe("ready");
  expect(result.current.options[0].modelId).toBe("B");
});

test("error retains previous list but successful empty refresh clears it", async () => {
  const client = { request: vi.fn().mockResolvedValueOnce(payload("A")).mockResolvedValueOnce({ ok:false }).mockResolvedValueOnce({ ok:true, modeller:[] }) };
  const { result } = renderHook(() => useModelCatalog(client, "a", "kod"));
  await act(async () => { await result.current.load(); await result.current.load(); });
  expect(result.current.state.status).toBe("error");
  expect(result.current.options[0].modelId).toBe("A");
  await act(async () => { await result.current.load(); });
  expect(result.current.state.status).toBe("ready");
  expect(result.current.options).toEqual([]);
});
