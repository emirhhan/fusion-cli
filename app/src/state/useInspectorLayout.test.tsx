import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { INSPECTOR_LAYOUT_STORAGE_KEY, useInspectorLayout } from "./useInspectorLayout";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("useInspectorLayout", () => {
  it("profesyonel masaüstü varsayılanlarıyla başlar", () => {
    const { result } = renderHook(() => useInspectorLayout());
    expect(result.current.width).toBe(420);
    expect(result.current.collapsed).toBe(false);
    expect(result.current.activeTab).toBe("files");
  });

  it("bozuk saklı genişliği sınırlar ve geçerli sekmeyi geri yükler", () => {
    localStorage.setItem(
      INSPECTOR_LAYOUT_STORAGE_KEY,
      JSON.stringify({ width: 999, collapsed: true, activeTab: "terminal" }),
    );
    const { result } = renderHook(() => useInspectorLayout());
    expect(result.current.width).toBe(680);
    expect(result.current.collapsed).toBe(true);
    expect(result.current.activeTab).toBe("terminal");
  });

  it("genişlik, daraltma ve sekme tercihini aynı kayıtta saklar", () => {
    const { result } = renderHook(() => useInspectorLayout());
    act(() => {
      result.current.setWidth(512);
      result.current.setCollapsed(true);
      result.current.setActiveTab("preview");
    });
    expect(JSON.parse(localStorage.getItem(INSPECTOR_LAYOUT_STORAGE_KEY) ?? "{}")).toEqual({
      activeTab: "preview",
      collapsed: true,
      width: 512,
    });
  });
});
