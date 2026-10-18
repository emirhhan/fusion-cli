import { Icon, type IconName } from "../ui/Icon";
import { useEffect, useState } from "react";
import "./MainRail.css";

/** En soldaki ana menünün bölümleri; sıra kullanıcının belirlediği sıradır. */
export type MainSection = "home" | "scheduled" | "library" | "media" | "kits";

interface RailItem {
  icon: IconName;
  id: MainSection;
  label: string;
}

export const MAIN_SECTIONS: readonly RailItem[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "scheduled", label: "Zamanlananlar", icon: "clock" },
  { id: "library", label: "Kitaplık", icon: "library" },
  { id: "media", label: "Görsel ve video üretimi", icon: "image" },
  { id: "kits", label: "Kits", icon: "sparkle" },
];

interface MainRailProps {
  active: MainSection;
  onSelect: (section: MainSection) => void;
  accountHostRef?: (node: HTMLDivElement | null) => void;
}

export function MainRail({ active, onSelect, accountHostRef }: MainRailProps) {
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setDismissed(true); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, []);
  return (
    <nav aria-label="Ana menü" className="main-rail">
      <div aria-hidden="true" className="main-rail__titlebar-spacer" data-tauri-drag-region />
      {MAIN_SECTIONS.map((item) => (
        <button
          aria-label={item.label}
          aria-describedby={`rail-tooltip-${item.id}`}
          data-tooltip-hidden={dismissed || undefined}
          aria-current={item.id === active ? "page" : undefined}
          className="main-rail__item"
          key={item.id}
          onClick={() => onSelect(item.id)}
          onMouseEnter={() => setDismissed(false)}
          onFocus={() => setDismissed(false)}
          type="button"
        >
          <Icon name={item.icon} size={22} />
          <span className="main-rail__label" id={`rail-tooltip-${item.id}`} role="tooltip">{item.label}</span>
        </button>
      ))}
      <div className="main-rail__account" ref={accountHostRef} />
    </nav>
  );
}
