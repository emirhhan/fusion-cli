import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useDictation, type DictationRuntime } from "./useDictation";

it("dikteyi taslakta tutar, otomatik göndermez ve başka oturum olayını yoksayar", async () => {
  let line: ((event: { session: number; line: string }) => void) | null = null;
  let ended: ((event: { session: number }) => void) | null = null;
  const stop = vi.fn(async () => undefined);
  const runtime: DictationRuntime = {
    onLine: async (handler) => { line = handler; return () => { line = null; }; },
    onEnded: async (handler) => { ended = handler; return () => { ended = null; }; },
    start: async () => 7,
    stop,
  };
  const onText = vi.fn();
  const { result } = renderHook(() => useDictation(onText, runtime));
  await act(async () => { await result.current.start("chat-1", "Eski metin"); });
  expect(result.current.listening).toBe(true);

  await act(async () => {
    line?.({ session: 8, line: JSON.stringify({ tur: "son", metin: "yanlış" }) });
    line?.({ session: 7, line: JSON.stringify({ tur: "kismi", metin: "merha" }) });
  });
  expect(onText).toHaveBeenLastCalledWith("chat-1", "Eski metin merha");
  await act(async () => {
    line?.({ session: 7, line: JSON.stringify({ tur: "son", metin: "merhaba" }) });
  });
  expect(onText).toHaveBeenLastCalledWith("chat-1", "Eski metin merhaba");
  expect(stop).toHaveBeenCalledTimes(1);
  expect(result.current.listening).toBe(false);
  expect(ended).toBeNull();
});

it("başlatma sürerken gelen metni korur ve iptal edilen geç başlangıcı dinlemez", async () => {
  let line: ((event: { session: number; line: string }) => void) | null = null;
  let resolveStart: ((session: number) => void) | null = null;
  const stop = vi.fn(async () => undefined);
  const runtime: DictationRuntime = {
    onLine: async (handler) => { line = handler; return () => { line = null; }; },
    onEnded: async () => () => undefined,
    start: () => new Promise<number>((resolve) => { resolveStart = resolve; }),
    stop,
  };
  const onText = vi.fn();
  const { result } = renderHook(() => useDictation(onText, runtime));
  let starting: Promise<void> | undefined;
  await act(async () => {
    starting = result.current.start("chat-1", "Taslak");
    await Promise.resolve();
  });
  await act(async () => {
    line?.({ session: 4, line: JSON.stringify({ tur: "kismi", metin: "merhaba" }) });
    resolveStart?.(4);
    await starting;
  });
  expect(onText).toHaveBeenCalledWith("chat-1", "Taslak merhaba");

  await act(async () => { await result.current.stop(); });
  expect(result.current.listening).toBe(false);
  expect(stop).toHaveBeenCalledTimes(1);
});
