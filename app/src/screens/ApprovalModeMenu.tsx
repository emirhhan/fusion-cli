import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Icon } from "../ui/Icon";
import "./ApprovalModeMenu.css";

/** İzin kipi — çekirdekteki `ApprovalMode` ile aynı değerler (`security` = Manuel). */
export type ApprovalMode = "auto" | "security" | "edits" | "plan" | "bypass";

interface ModeInfo {
  id: ApprovalMode;
  label: string;
  hint: string;
}

/** Menü sırası Claude'un izin menüsüyle aynıdır; rakam kısayolu bu sıradır. */
export const APPROVAL_MODES: readonly ModeInfo[] = [
  { id: "auto", label: "Otomatik", hint: "Fusion karar verir; yalnız riskli işlemde sorar" },
  { id: "security", label: "Manuel", hint: "Okuma dışındaki her işlemden önce sorar" },
  { id: "edits", label: "Düzenlemeleri kabul et", hint: "Dosya düzenlemelerini sormadan uygular; komutları sorar" },
  { id: "plan", label: "Plan", hint: "Değiştirmeden önce plan çıkarır; yalnız okur" },
  { id: "bypass", label: "İzinleri atla", hint: "Hiçbir şey sormaz; silinenler yine Fusion çöpüne gider" },
];

/** Shift+Tab döngüsü. "İzinleri atla" BİLEREK yok: yanlışlıkla açılmamalı. */
const CYCLE: readonly ApprovalMode[] = ["auto", "security", "edits", "plan"];

export function approvalInfo(mode: ApprovalMode): ModeInfo {
  return APPROVAL_MODES.find((item) => item.id === mode) ?? APPROVAL_MODES[0];
}

export function nextApprovalMode(mode: ApprovalMode): ApprovalMode {
  const index = CYCLE.indexOf(mode);
  return CYCLE[(index + 1) % CYCLE.length];
}

/** Composer'daki izin kipi seçici: Claude'daki gibi açıklamalı, rakam kısayollu menü. */
export function ApprovalModeMenu({
  mode,
  onChange,
}: {
  mode: ApprovalMode;
  onChange: (mode: ApprovalMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const current = approvalInfo(mode);

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  useEffect(() => {
    if (open) items.current[focus]?.focus();
  }, [open, focus]);

  const choose = (next: ApprovalMode) => {
    setOpen(false);
    if (next !== mode) onChange(next);
  };

  const toggle = () => {
    setFocus(Math.max(0, APPROVAL_MODES.findIndex((item) => item.id === mode)));
    setOpen((value) => !value);
  };

  const onMenuKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const digit = Number(event.key);
    if (Number.isInteger(digit) && digit >= 1 && digit <= APPROVAL_MODES.length) {
      event.preventDefault();
      choose(APPROVAL_MODES[digit - 1].id);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setFocus((value) => (value + step + APPROVAL_MODES.length) % APPROVAL_MODES.length);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="approval-menu" ref={box}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`İzin modu: ${current.label}. Değiştirmek için tıkla ya da Shift+Tab.`}
        className="composer__approval approval-menu__trigger"
        data-mode={mode}
        onClick={toggle}
        title={current.hint}
        type="button"
      >
        {current.label}
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div aria-label="İzin modu" className="approval-menu__list" onKeyDown={onMenuKey} role="menu">
          {APPROVAL_MODES.map((item, index) => (
            <button
              aria-checked={item.id === mode}
              className="approval-menu__item"
              data-mode={item.id}
              key={item.id}
              onClick={() => choose(item.id)}
              ref={(element) => {
                items.current[index] = element;
              }}
              role="menuitemradio"
              tabIndex={index === focus ? 0 : -1}
              type="button"
            >
              <span className="approval-menu__text">
                <strong>{item.label}</strong>
                <small>{item.hint}</small>
              </span>
              <span aria-hidden="true" className="approval-menu__key">
                {item.id === mode ? "✓" : index + 1}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
