import { Icon, type IconName } from "../ui/Icon";
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
}

export function MainRail({ active, onSelect }: MainRailProps) {
  return (
    <nav aria-label="Ana menü" className="main-rail">
      <div aria-hidden="true" className="main-rail__titlebar-spacer" data-tauri-drag-region />
      {MAIN_SECTIONS.map((item) => (
        <button
          aria-current={item.id === active ? "page" : undefined}
          className="main-rail__item"
          key={item.id}
          onClick={() => onSelect(item.id)}
          type="button"
        >
          <Icon name={item.icon} size={22} />
          <span className="main-rail__label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
