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

test("başka oturuma geçince eski katalog başarılı olsa da yeni listeyi ezmez", async () => {
  const a = deferred(), b = deferred();
  const first: CatalogClient = { request: vi.fn(() => a.promise) };
  const second: CatalogClient = { request: vi.fn(() => b.promise) };
  const { result, rerender } = renderHook(({ client, id }) => useModelCatalog(client, id, "kod"), { initialProps: { client: first, id: "a" } });
  let loadA!: Promise<void>;
  act(() => { loadA = result.current.load(); });
  rerender({ client: second, id: "b" });
  let loadB!: Promise<void>;
  act(() => { loadB = result.current.load(); });
  await act(async () => { b.resolve(payload("B")); await loadB; });
  await act(async () => { a.resolve(payload("A")); await loadA; });
  expect(result.current.options.map((option) => option.modelId)).toEqual(["B"]);
  expect(result.current.state.status).toBe("ready");
});

test("eski isteğin reddi yeni başarılı listeyi hata yapmaz", async () => {
  const old = deferred(), fresh = deferred();
  const client = { request: vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise) };
  const { result } = renderHook(() => useModelCatalog(client, "a", "kod"));
  let first!: Promise<void>, second!: Promise<void>;
  act(() => { first = result.current.load(); second = result.current.load(); });
  await act(async () => { fresh.resolve(payload("B")); await second; });
  await act(async () => { old.reject(new Error("eski kaynak")); await first; });
  expect(result.current.state.status).toBe("ready");
  expect(result.current.options[0].modelId).toBe("B");
});

test("ok:false hata; son seçenek korunur ve yeniden deneme boş başarı olabilir", async () => {
  const client = { request: vi.fn().mockResolvedValueOnce(payload("A")).mockResolvedValueOnce({ ok: false }).mockResolvedValueOnce({ ok: true, modeller: [] }) };
  const { result } = renderHook(() => useModelCatalog(client, "a", "kod"));
  await act(async () => { await result.current.load(); });
  await act(async () => { await result.current.load(); });
  expect(result.current.state.status).toBe("error");
  expect(result.current.options[0].modelId).toBe("A");
  await act(async () => { await result.current.load(); });
  expect(result.current.state.status).toBe("ready");
  expect(result.current.options).toEqual([]);
});
