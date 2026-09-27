import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useNavigationHistory } from "./useNavigationHistory";

describe("useNavigationHistory", () => {
  it("başlangıçta geri ve ileri gidemez", () => {
    const { result } = renderHook(() => useNavigationHistory("chat"));
    expect(result.current.current).toBe("chat");
    expect(result.current.canGoBack).toBe(false);
    expect(result.current.canGoForward).toBe(false);
  });

  it("push sonrası geri gidebilir, geri gidince ileri gidebilir", () => {
    const { result } = renderHook(() => useNavigationHistory("chat"));
    act(() => result.current.push("settings"));
    expect(result.current.current).toBe("settings");
    expect(result.current.canGoBack).toBe(true);

    act(() => result.current.back());
    expect(result.current.current).toBe("chat");
    expect(result.current.canGoForward).toBe(true);

    act(() => result.current.forward());
    expect(result.current.current).toBe("settings");
    expect(result.current.canGoForward).toBe(false);
  });

  it("aynı sayfaya tekrar push yeni girdi eklemez", () => {
    const { result } = renderHook(() => useNavigationHistory("chat"));
    act(() => result.current.push("chat"));
    expect(result.current.canGoBack).toBe(false);
  });

  it("geri gidip yeni sayfaya geçince ileri yığını temizlenir", () => {
    const { result } = renderHook(() => useNavigationHistory("chat"));
    act(() => result.current.push("settings"));
    act(() => result.current.push("help"));
    act(() => result.current.back());
    expect(result.current.current).toBe("settings");

    act(() => result.current.push("skills"));
    expect(result.current.current).toBe("skills");
    expect(result.current.canGoForward).toBe(false);

    act(() => result.current.back());
    expect(result.current.current).toBe("settings");
  });

  it("yığının başında geri, sonunda ileri hiçbir şey yapmaz", () => {
    const { result } = renderHook(() => useNavigationHistory("chat"));
    act(() => result.current.back());
    expect(result.current.current).toBe("chat");

    act(() => result.current.push("settings"));
    act(() => result.current.forward());
    expect(result.current.current).toBe("settings");
  });
});
