import { useCallback, useEffect, useState } from "react";
import type { InspectorTabId } from "../screens/Inspector";

export const INSPECTOR_LAYOUT_STORAGE_KEY = "fusion.inspector.layout.v1";
export const INSPECTOR_MIN_WIDTH = 320;
export const INSPECTOR_MAX_WIDTH = 680;
export const INSPECTOR_DEFAULT_WIDTH = 420;
export const INSPECTOR_COLLAPSED_WIDTH = 56;

const inspectorTabs = new Set<InspectorTabId>([
  "files", "changes", "terminal", "processes", "tests", "preview", "context",
]);

interface InspectorLayoutState {
  activeTab: InspectorTabId;
  collapsed: boolean;
  width: number;
}

const defaults: InspectorLayoutState = {
  activeTab: "files",
  collapsed: false,
  width: INSPECTOR_DEFAULT_WIDTH,
};

export function clampInspectorWidth(value: number): number {
  if (!Number.isFinite(value)) return INSPECTOR_DEFAULT_WIDTH;
  return Math.min(INSPECTOR_MAX_WIDTH, Math.max(INSPECTOR_MIN_WIDTH, Math.round(value)));
}

function readInspectorLayout(): InspectorLayoutState {
  try {
    const parsed = JSON.parse(
      localStorage.getItem(INSPECTOR_LAYOUT_STORAGE_KEY) ?? "null",
    ) as Partial<InspectorLayoutState> | null;
    return {
      activeTab: inspectorTabs.has(parsed?.activeTab as InspectorTabId)
        ? parsed?.activeTab as InspectorTabId
        : defaults.activeTab,
      collapsed: typeof parsed?.collapsed === "boolean" ? parsed.collapsed : defaults.collapsed,
      width: clampInspectorWidth(typeof parsed?.width === "number" ? parsed.width : defaults.width),
    };
  } catch {
    return defaults;
  }
}

export function useInspectorLayout() {
  const [layout, setLayout] = useState<InspectorLayoutState>(readInspectorLayout);

  useEffect(() => {
    try {
      localStorage.setItem(INSPECTOR_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
    } catch {
      // Yerel tercih yazılamasa da çalışma paneli kullanılabilir kalır.
    }
  }, [layout]);

  const setActiveTab = useCallback((activeTab: InspectorTabId) => {
    setLayout((current) => current.activeTab === activeTab ? current : { ...current, activeTab });
  }, []);
  const setCollapsed = useCallback((collapsed: boolean) => {
    setLayout((current) => current.collapsed === collapsed ? current : { ...current, collapsed });
  }, []);
  const setWidth = useCallback((width: number) => {
    const next = clampInspectorWidth(width);
    setLayout((current) => current.width === next ? current : { ...current, width: next });
  }, []);

  return {
    ...layout,
    setActiveTab,
    setCollapsed,
    setWidth,
  };
}
