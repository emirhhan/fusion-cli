import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Icon } from "../ui/Icon";

/**
 * Composer'daki efor (düşünme yoğunluğu) menüsü; Cmd/Ctrl+Shift+E ile açılır (Claude Code
 * Desktop, #444). Seçim `/effort <düzey>` komutuyla uygulanır (CLI ile aynı yol); model
 * düzeyi desteklemiyorsa çekirdek en yakınına iner ve nedenini yazar.
 */
export const EFFORT_LEVELS = [
  { id: "auto", label: "Modele bırak" },
  { id: "low", label: "low" },
  { id: "medium", label: "medium" },
  { id: "high", label: "high" },
  { id: "xhigh", label: "xhigh" },
  { id: "max", label: "max" },
] as const;

export function EffortMenu({ onSelect, disabled = false }: { onSelect: (level: string) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (disabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !(event.metaKey || event.ctrlKey) || !event.shiftKey || event.altKey) return;
      if (event.code !== "KeyE" && event.key.toLowerCase() !== "e") return;
      event.preventDefault();
      setFocus(0);
      setOpen((value) => !value);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    items.current[focus]?.focus();
    const outside = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open, focus]);

  const choose = (level: string) => {
    setOpen(false);
    trigger.current?.focus();
    onSelect(level);
  };
  const onMenuKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setFocus((value) => (value + step + EFFORT_LEVELS.length) % EFFORT_LEVELS.length);
    } else if (event.key === "Escape" || event.key === "Tab") {
      if (event.key === "Escape") event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    }
  };

  return (
    <div className="approval-menu" ref={box}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Efor: düşünme yoğunluğunu seç (Cmd/Ctrl+Shift+E)"
        className="composer__approval approval-menu__trigger"
        disabled={disabled}
        onClick={() => { setFocus(0); setOpen((value) => !value); }}
        ref={trigger}
        title="Düşünme yoğunluğu (/effort)"
        type="button"
      >
        Efor
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div aria-label="Efor" className="approval-menu__list" onKeyDown={onMenuKey} role="menu">
          {EFFORT_LEVELS.map((item, index) => (
            <button
              className="approval-menu__item"
              key={item.id}
              onClick={() => choose(item.id)}
              ref={(element) => { items.current[index] = element; }}
              role="menuitem"
              tabIndex={index === focus ? 0 : -1}
              type="button"
            >
              <span className="approval-menu__text"><strong>{item.label}</strong></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
