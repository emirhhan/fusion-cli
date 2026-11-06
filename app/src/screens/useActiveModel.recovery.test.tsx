import { StrictMode, type PropsWithChildren } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useActiveModel } from "./useActiveModel";
import type { CatalogClient } from "./useModelCatalog";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const valid = (agent = "pinned-model") => ({ ok: true, model: { agent, agent_label: "" } });

// Removing the bootstrap wait would read before the session owns its backend identity.
test("waits for the exact bootstrap promise, then reads the configured model", async () => {
  const bootstrap = deferred<boolean>();
  const client: CatalogClient = { request: vi.fn(async () => valid()) };
  const { result } = renderHook(() => useActiveModel(client, "A", 0, bootstrap.promise));
  expect(result.current.pending).toBe(true);
  expect(client.request).not.toHaveBeenCalled();
  await act(async () => bootstrap.resolve(true));
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  expect(result.current.pending).toBe(false);
  expect(result.current.error).toBe("");
  expect(client.request).toHaveBeenCalledExactlyOnceWith("kontrol.durum", {});
});

test.each([undefined, null, 7, {}, "", "   "])("recovers once from malformed agent %j", async (agent) => {
  const client: CatalogClient = { request: vi.fn().mockResolvedValueOnce({ ok: true, model: { agent } }).mockResolvedValueOnce(valid()) };
  const { result } = renderHook(() => useActiveModel(client, "A", 0));
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  expect(client.request).toHaveBeenCalledTimes(2);
  expect(vi.mocked(client.request).mock.calls.every(([name]) => name === "kontrol.durum")).toBe(true);
});

test.each(["reject", "ok-false"])("bounded recovery from %s; both failures expose read-only manual retry", async (failure) => {
  const request = vi.fn();
  if (failure === "reject") request.mockRejectedValueOnce(new Error("secret raw failure"));
  else request.mockResolvedValueOnce({ ok: false });
  request.mockResolvedValueOnce({ ok: false }).mockResolvedValueOnce(valid());
  const client: CatalogClient = { request };
  const { result } = renderHook(() => useActiveModel(client, "A", 0));
  await waitFor(() => expect(result.current.error).toMatch(/okunamadı/));
  expect(result.current.error).not.toContain("secret");
  expect(result.current.pending).toBe(false);
  expect(result.current.model).toBe("");
  expect(request).toHaveBeenCalledTimes(2);
  await act(async () => result.current.retry());
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  expect(request).toHaveBeenCalledTimes(3);
  expect(request.mock.calls.every(([name]) => name === "kontrol.durum")).toBe(true);
});

test("preserves last valid same-owner model with explicit refresh failure", async () => {
  const request = vi.fn().mockResolvedValueOnce(valid()).mockRejectedValue(new Error("refresh"));
  const client = { request };
  const { result, rerender } = renderHook(({ revision }) => useActiveModel(client, "A", revision), { initialProps: { revision: 0 } });
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  rerender({ revision: 1 });
  await waitFor(() => expect(result.current.error).toMatch(/son okunan model/));
  expect(result.current.model).toBe("pinned-model");
});

test("a new client with the same session ID never inherits model or late bootstrap", async () => {
  const bootstrap = deferred<boolean>();
  const old: CatalogClient = { request: vi.fn(async () => valid("old")) };
  const next: CatalogClient = { request: vi.fn(async () => valid("new")) };
  const { result, rerender } = renderHook(({ client, ready }) => useActiveModel(client, "same", 0, ready), { initialProps: { client: old, ready: bootstrap.promise as Promise<boolean> | undefined } });
  rerender({ client: next, ready: undefined });
  await waitFor(() => expect(result.current.model).toBe("new"));
  await act(async () => bootstrap.resolve(true));
  expect(old.request).not.toHaveBeenCalled();
  expect(result.current.model).toBe("new");
});

test("ignores late earlier revision and stops recovery after unmount", async () => {
  const late = deferred<Record<string, unknown>>();
  const request = vi.fn().mockReturnValueOnce(late.promise).mockResolvedValueOnce(valid("new"));
  const client = { request };
  const { result, rerender, unmount } = renderHook(({ revision }) => useActiveModel(client, "A", revision), { initialProps: { revision: 0 } });
  rerender({ revision: 1 });
  await waitFor(() => expect(result.current.model).toBe("new"));
  unmount();
  await act(async () => late.resolve({ ok: false }));
  expect(request).toHaveBeenCalledTimes(2);
});

test("failed bootstrap never reads model; delayed bootstrap after unmount never reads either", async () => {
  const client = { request: vi.fn(async () => valid()) };
  const failed = Promise.resolve(false);
  const { result, unmount } = renderHook(() => useActiveModel(client, "A", 0, failed));
  await waitFor(() => expect(result.current.error).toMatch(/okunamadı/));
  expect(client.request).not.toHaveBeenCalled();
  unmount();
  const bootstrap = deferred<boolean>();
  const mounted = renderHook(() => useActiveModel(client, "B", 0, bootstrap.promise));
  mounted.unmount();
  await act(async () => bootstrap.resolve(true));
  expect(client.request).not.toHaveBeenCalled();
});

test("StrictMode waits for bootstrap and performs only the surviving read", async () => {
  const bootstrap = deferred<boolean>();
  const client = { request: vi.fn(async () => valid()) };
  const wrapper = ({ children }: PropsWithChildren) => <StrictMode>{children}</StrictMode>;
  const { result } = renderHook(() => useActiveModel(client, "A", 0, bootstrap.promise), { wrapper });
  await act(async () => bootstrap.resolve(true));
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  expect(client.request).toHaveBeenCalledTimes(1);
});

test.each(["reject", "ok-false"])("an initial %s recovers automatically without changing the configured model", async (failure) => {
  const request = vi.fn();
  if (failure === "reject") request.mockRejectedValueOnce(new Error("temporary"));
  else request.mockResolvedValueOnce({ ok: false });
  request.mockResolvedValueOnce(valid());
  const client = { request };
  const { result } = renderHook(() => useActiveModel(client, "A", 0));
  await waitFor(() => expect(result.current.model).toBe("pinned-model"));
  expect(result.current.label).toBe("");
  expect(result.current.error).toBe("");
  expect(request.mock.calls).toEqual([["kontrol.durum", {}], ["kontrol.durum", {}]]);
});
