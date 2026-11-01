import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { autoPolicyDisabled, onAutoGateChange } from "../sessions/autoGate";
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
  { id: "edits", label: "Düzenlemeleri kabul et", hint: "Dosya düzenlemelerini ve mkdir, touch, rm, rmdir, mv, cp, sed komutlarını çalışma dizininde sormadan uygular; öteki komutları sorar" },
  { id: "plan", label: "Plan", hint: "Değiştirmeden önce plan çıkarır; yalnız okur" },
  { id: "bypass", label: "İzinleri atla", hint: "Hiçbir şey sormaz; silinenler yine Fusion çöpüne gider" },
];

/** Shift+Tab döngüsü. "İzinleri atla" BİLEREK yok: yanlışlıkla açılmamalı. */
const CYCLE: readonly ApprovalMode[] = ["auto", "security", "edits", "plan"];

/** `disableAutoMode: "disable"` (#85): auto menüden ve döngüden çıkar (seçiliyse görünür kalır). */
function visibleModes(current: ApprovalMode): readonly ModeInfo[] {
  if (!autoPolicyDisabled() || current === "auto") return APPROVAL_MODES;
  return APPROVAL_MODES.filter((item) => item.id !== "auto");
}

export function approvalInfo(mode: ApprovalMode): ModeInfo {
  return APPROVAL_MODES.find((item) => item.id === mode) ?? APPROVAL_MODES[0];
}

export function nextApprovalMode(mode: ApprovalMode): ApprovalMode {
  const cycle = autoPolicyDisabled() ? CYCLE.filter((item) => item !== "auto") : CYCLE;
  const index = cycle.indexOf(mode);
  return cycle[(index + 1) % cycle.length];
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
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const current = approvalInfo(mode);
  const [, setAutoGate] = useState(0);
  const modes = visibleModes(mode);

  useEffect(() => onAutoGateChange(() => setAutoGate((value) => value + 1)), []);

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
    // Menü kapanınca odak tetikleyiciye döner; yoksa klavye kullanıcısı gövdede kalır (U1-49).
    trigger.current?.focus();
    if (next !== mode) onChange(next);
  };

  const toggle = () => {
    setFocus(Math.max(0, modes.findIndex((item) => item.id === mode)));
    setOpen((value) => !value);
  };

  const onMenuKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const digit = Number(event.key);
    if (Number.isInteger(digit) && digit >= 1 && digit <= modes.length) {
      event.preventDefault();
      choose(modes[digit - 1].id);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setFocus((value) => (value + step + modes.length) % modes.length);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setFocus(event.key === "Home" ? 0 : modes.length - 1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    } else if (event.key === "Tab") {
      // Tab menüden çıkar; açık kalan menü sonraki odak noktalarını örterdi.
      setOpen(false);
      trigger.current?.focus();
    }
  };

  return (
    <div className="approval-menu" ref={box}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`İzin modu: ${current.label}. Değiştirmek için tıkla ya da Shift+Tab.`}
        className="composer__approval approval-menu__trigger"
        ref={trigger}
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
          {modes.map((item, index) => (
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
