import { useEffect, useRef, useState } from "react";

/**
 * Kenar çubuğunun "Group and sort" menüsü (Claude Desktop, #443).
 *
 * Gruplama: Projeye göre (varsayılan) ya da gruplama yok (tek düz liste). Sıralama: son etkinlik
 * (Claude'daki "Recency"); sabitlenen sohbetler her görünümde başta kalır. Tercih bu
 * bilgisayarda saklanır.
 */
export type SidebarGrouping = "project" | "none";
export const SIDEBAR_GROUPING_KEY = "fusion.sidebar.grouping.v1";

function readGrouping(): SidebarGrouping {
  try {
    return localStorage.getItem(SIDEBAR_GROUPING_KEY) === "none" ? "none" : "project";
  } catch {
    return "project";
  }
}

export function useSidebarGrouping(): [SidebarGrouping, (next: SidebarGrouping) => void] {
  const [grouping, setGrouping] = useState<SidebarGrouping>(readGrouping);
  const change = (next: SidebarGrouping) => {
    setGrouping(next);
    try { localStorage.setItem(SIDEBAR_GROUPING_KEY, next); } catch { /* bu pencerede geçerli kalır */ }
  };
  return [grouping, change];
}

const GROUPINGS: { id: SidebarGrouping; label: string }[] = [
  { id: "project", label: "Projeye göre" },
  { id: "none", label: "Gruplama yok" },
];

export function GroupSortMenu({ grouping, onChange }: { grouping: SidebarGrouping; onChange: (next: SidebarGrouping) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <span className="sidebar__group-sort" ref={box}>
      <button aria-expanded={open} aria-haspopup="menu" aria-label="Grupla ve sırala" onClick={() => setOpen((value) => !value)} title="Grupla ve sırala" type="button">⇅</button>
      {open && (
        <div aria-label="Grupla ve sırala" className="sidebar__project-menu sidebar__projects-menu" role="menu">
          <p className="sidebar__projects-menu-empty">Grupla</p>
          {GROUPINGS.map((item) => (
            <button aria-checked={grouping === item.id} key={item.id} onClick={() => { onChange(item.id); setOpen(false); }} role="menuitemradio" type="button">{item.label}</button>
          ))}
          <p className="sidebar__projects-menu-empty">Sırala</p>
          <button aria-checked disabled role="menuitemradio" type="button">Son etkinliğe göre</button>
        </div>
      )}
    </span>
  );
}
