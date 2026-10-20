import { cleanup, renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LAYOUT_STORAGE_KEY, useLayout } from "./useLayout";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("useLayout", () => {
  it("güvenli görünüm varsayılanlarıyla başlar", () => {
    const { result } = renderHook(() => useLayout());
    expect(result.current.sidebarCollapsed).toBe(false);
    expect(result.current.inspectorOpen).toBe(true);
  });

  it("panel durumlarını değiştirir ve saklar", () => {
    const { result } = renderHook(() => useLayout());
    act(() => {
      result.current.toggleSidebar();
      result.current.closeInspector();
    });
    expect(result.current.sidebarCollapsed).toBe(true);
    expect(result.current.inspectorOpen).toBe(false);
    expect(JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) ?? "{}")).toEqual({
      inspectorOpen: false,
      sidebarCollapsed: true,
    });
  });

  it("saklı görünüm tercihini geri yükler", () => {
    localStorage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({ inspectorOpen: false, sidebarCollapsed: true }),
    );
    const { result } = renderHook(() => useLayout());
    expect(result.current.sidebarCollapsed).toBe(true);
    expect(result.current.inspectorOpen).toBe(false);
  });
});
