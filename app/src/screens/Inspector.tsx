import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import {
  clampInspectorWidth,
  INSPECTOR_DEFAULT_WIDTH,
  INSPECTOR_MAX_WIDTH,
  INSPECTOR_MIN_WIDTH,
} from "../state/useInspectorLayout";
import type { IconName } from "../ui/Icon";
import { Icon } from "../ui/Icon";
import "./Inspector.css";

type InspectorStatus = "ready" | "loading" | "error";
export type InspectorTabId = "files" | "changes" | "terminal" | "processes" | "tests" | "preview" | "context";

const tabs: { id: InspectorTabId; label: string; icon: IconName }[] = [
  { id: "files", label: "Dosyalar", icon: "files" },
  { id: "changes", label: "Değişiklikler", icon: "changes" },
  { id: "terminal", label: "Terminal", icon: "terminal" },
  { id: "processes", label: "Süreçler", icon: "panel" },
  { id: "tests", label: "Testler", icon: "tests" },
  { id: "preview", label: "Önizleme", icon: "preview" },
  { id: "context", label: "Bağlam", icon: "skills" },
];

interface InspectorProps {
  activeTab?: InspectorTabId;
  collapsed?: boolean;
  content?: Partial<Record<InspectorTabId, ReactNode>>;
  errorMessage?: string;
  onActiveTabChange?: (tab: InspectorTabId) => void;
  onCollapsedChange?: (collapsed: boolean) => void;
  onWidthChange?: (width: number) => void;
  /**
   * Dışarıdan istenen sekme. Ders adımı "proje sekmesini aç" dediğinde
   * kullanılır; kullanıcının elle seçtiği sekmeyi kilitlemez — istek
   * değiştiğinde bir kez uygulanır, sonra denetim yine kullanıcıdadır.
   */
  requestedTab?: InspectorTabId | null;
  status?: InspectorStatus;
  width?: number;
}

export function Inspector({
  activeTab: controlledActiveTab,
  collapsed = false,
  content = {},
  errorMessage = "Denetçi yüklenemedi",
  onActiveTabChange,
  onCollapsedChange,
  onWidthChange,
  requestedTab = null,
  status = "ready",
  width = INSPECTOR_DEFAULT_WIDTH,
}: InspectorProps) {
  const [internalActiveTab, setInternalActiveTab] = useState<InspectorTabId>("files");
  const appliedRequestedTab = useRef<InspectorTabId | null>(null);
  const resizeCleanup = useRef<() => void>(() => undefined);
  const activeTab = controlledActiveTab ?? internalActiveTab;
  const setActiveTab = (tab: InspectorTabId) => {
    if (controlledActiveTab === undefined) setInternalActiveTab(tab);
    onActiveTabChange?.(tab);
  };
  useEffect(() => {
    if (!requestedTab) {
      appliedRequestedTab.current = null;
      return;
    }
    if (appliedRequestedTab.current === requestedTab) return;
    appliedRequestedTab.current = requestedTab;
    if (controlledActiveTab === undefined) setInternalActiveTab(requestedTab);
    onActiveTabChange?.(requestedTab);
  }, [controlledActiveTab, onActiveTabChange, requestedTab]);
  useEffect(() => () => resizeCleanup.current(), []);
  useEffect(() => {
    if (collapsed) resizeCleanup.current();
  }, [collapsed]);
  const activeIndex = tabs.findIndex((tab) => tab.id === activeTab);
  const selectAt = (index: number) => {
    const tab = tabs[(index + tabs.length) % tabs.length];
    setActiveTab(tab.id);
    if (collapsed) onCollapsedChange?.(false);
    document.getElementById(`inspector-tab-${tab.id}`)?.focus();
  };
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectAt(activeIndex + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectAt(activeIndex - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      selectAt(0);
    } else if (event.key === "End") {
      event.preventDefault();
      selectAt(tabs.length - 1);
    }
  };
  const active = tabs[activeIndex];
  const safeWidth = clampInspectorWidth(width);
  const onResizeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next: number | null = null;
    if (event.key === "ArrowLeft") next = safeWidth - 16;
    else if (event.key === "ArrowRight") next = safeWidth + 16;
    else if (event.key === "Home") next = INSPECTOR_MIN_WIDTH;
    else if (event.key === "End") next = INSPECTOR_MAX_WIDTH;
    if (next === null) return;
    event.preventDefault();
    onWidthChange?.(clampInspectorWidth(next));
  };
  const onResizePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!onWidthChange || event.button !== 0) return;
    event.preventDefault();
    resizeCleanup.current();
    const startX = event.clientX;
    const startWidth = safeWidth;
    const move = (nextEvent: PointerEvent) => {
      onWidthChange(clampInspectorWidth(startWidth + startX - nextEvent.clientX));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      resizeCleanup.current = () => undefined;
    };
    resizeCleanup.current = stop;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
  };

  return (
    <div className="inspector" data-collapsed={collapsed}>
      {!collapsed && (
        <div
          aria-label="Çalışma panelini yeniden boyutlandır"
          aria-orientation="vertical"
          aria-valuemax={INSPECTOR_MAX_WIDTH}
          aria-valuemin={INSPECTOR_MIN_WIDTH}
          aria-valuenow={safeWidth}
          className="inspector__resize-handle"
          onKeyDown={onResizeKeyDown}
          onPointerDown={onResizePointerDown}
          role="separator"
          tabIndex={0}
        />
      )}
      <div className="inspector__topbar">
        <div aria-label="Denetçi araçları" className="inspector__tabs" role="tablist">
          {tabs.map((tab) => (
            <button
              aria-controls={collapsed ? undefined : `inspector-panel-${tab.id}`}
              aria-selected={activeTab === tab.id}
              id={`inspector-tab-${tab.id}`}
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                if (collapsed) onCollapsedChange?.(false);
              }}
              onKeyDown={onTabKeyDown}
              role="tab"
              tabIndex={activeTab === tab.id ? 0 : -1}
              title={tab.label}
              type="button"
            >
              <Icon name={tab.icon} size={17} />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
        <button
          aria-label={collapsed ? "Çalışma panelini genişlet" : "Çalışma panelini daralt"}
          className="inspector__collapse"
          onClick={() => onCollapsedChange?.(!collapsed)}
          title={collapsed ? "Genişlet" : "Daralt"}
          type="button"
        >
          <Icon name="chevron" size={17} />
        </button>
      </div>
      {!collapsed && (
        <section
          aria-labelledby={`inspector-tab-${active.id}`}
          className="inspector__panel"
          id={`inspector-panel-${active.id}`}
          role="tabpanel"
        >
          <div className="inspector__panel-title">
            <Icon name={active.icon} size={18} />
            <h2>{active.label}</h2>
          </div>
          {status === "loading" ? (
            <p className="inspector__state">Yükleniyor…</p>
          ) : status === "error" ? (
            <p className="inspector__state inspector__state--error" role="alert">{errorMessage}</p>
          ) : content[active.id] ? (
            content[active.id]
          ) : (
            <div className="inspector__empty">
              <p>Henüz bir proje seçilmedi.</p>
              <span>Bir proje açtığında {active.label.toLocaleLowerCase("tr")} burada görünür.</span>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
