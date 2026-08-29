import { useState, type KeyboardEvent, type ReactNode } from "react";
import type { IconName } from "../ui/Icon";
import { Icon } from "../ui/Icon";
import "./Inspector.css";

type InspectorStatus = "ready" | "loading" | "error";
type InspectorTabId = "files" | "changes" | "terminal" | "processes" | "tests" | "preview" | "context";

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
  content?: Partial<Record<InspectorTabId, ReactNode>>;
  errorMessage?: string;
  status?: InspectorStatus;
}

export function Inspector({ content = {}, errorMessage = "Denetçi yüklenemedi", status = "ready" }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTabId>("files");
  const activeIndex = tabs.findIndex((tab) => tab.id === activeTab);
  const selectAt = (index: number) => {
    const tab = tabs[(index + tabs.length) % tabs.length];
    setActiveTab(tab.id);
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

  return (
    <div className="inspector">
      <div aria-label="Denetçi araçları" className="inspector__tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            aria-controls={`inspector-panel-${tab.id}`}
            aria-selected={activeTab === tab.id}
            id={`inspector-tab-${tab.id}`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
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
    </div>
  );
}
