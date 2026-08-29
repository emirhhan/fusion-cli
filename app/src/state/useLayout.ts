import { useEffect, useState } from "react";

export const LAYOUT_STORAGE_KEY = "fusion.layout";

interface LayoutState {
  inspectorOpen: boolean;
  sidebarCollapsed: boolean;
}

const defaults: LayoutState = { inspectorOpen: true, sidebarCollapsed: false };

function readLayout(): LayoutState {
  try {
    const parsed = JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) ?? "null") as Partial<LayoutState> | null;
    return {
      inspectorOpen:
        typeof parsed?.inspectorOpen === "boolean" ? parsed.inspectorOpen : defaults.inspectorOpen,
      sidebarCollapsed:
        typeof parsed?.sidebarCollapsed === "boolean"
          ? parsed.sidebarCollapsed
          : defaults.sidebarCollapsed,
    };
  } catch {
    return defaults;
  }
}

export function useLayout() {
  const [layout, setLayout] = useState<LayoutState>(readLayout);

  useEffect(() => {
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
    } catch {
      // Görünüm tercihi saklanamasa da paneller kullanılabilir kalır.
    }
  }, [layout]);

  return {
    ...layout,
    closeInspector: () => setLayout((current) => ({ ...current, inspectorOpen: false })),
    toggleInspector: () =>
      setLayout((current) => ({ ...current, inspectorOpen: !current.inspectorOpen })),
    toggleSidebar: () =>
      setLayout((current) => ({ ...current, sidebarCollapsed: !current.sidebarCollapsed })),
  };
}
