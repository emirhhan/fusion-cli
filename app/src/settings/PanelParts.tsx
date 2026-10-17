import { useId, type ReactNode } from "react";
import "./Panels.css";

/**
 * Zeka ve Uzaktan Erişim ekranlarının ortak yapı taşları.
 *
 * Ayarlar penceresindeki diğer paneller gibi satır tabanlıdır: sol tarafta başlık ve
 * açıklama, sağ tarafta denetim. Renkler ve yarıçaplar yalnız tasarım jetonlarından gelir.
 */

export function PanelIntro({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <h3 className="settings__section-heading">{title}</h3>
      <p className="px-lead">{children}</p>
    </>
  );
}

export function PanelGroup({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="px-group">
      <header className="px-group__head">
        <h4>{title}</h4>
        {note && <p>{note}</p>}
      </header>
      <div className="px-group__body">{children}</div>
    </section>
  );
}

interface ToggleRowProps {
  checked: boolean;
  disabled?: boolean;
  title: string;
  description?: string;
  /** Kısa not rozeti: ör. "Maliyet: 1 çağrı". */
  chip?: string;
  warning?: string;
  onChange: (checked: boolean) => void;
}

export function ToggleRow({ checked, disabled, title, description, chip, warning, onChange }: ToggleRowProps) {
  const id = useId();
  return (
    <div className="px-row" data-on={checked}>
      <div className="px-row__text">
        <label className="px-row__title" htmlFor={id}>{title}</label>
        {description && <p className="px-row__hint">{description}</p>}
        {(chip || warning) && (
          <div className="px-row__meta">
            {chip && <small className="px-chip">{chip}</small>}
            {warning && <small className="px-chip px-chip--warn">{warning}</small>}
          </div>
        )}
      </div>
      <input
        checked={checked}
        className="px-switch"
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.checked)}
        role="switch"
        type="checkbox"
      />
    </div>
  );
}

interface ChoiceOption { value: string; title: string; description?: string }

interface ChoiceCardsProps {
  legend: string;
  name: string;
  value: string;
  options: ChoiceOption[];
  disabled?: boolean;
  note?: string;
  onChange: (value: string) => void;
}

/** Birbirini dışlayan seçenekler: işaretli olan kart vurgulanır. */
export function ChoiceCards({ legend, name, value, options, disabled, note, onChange }: ChoiceCardsProps) {
  return (
    <fieldset className="px-choices" disabled={disabled}>
      <legend>{legend}</legend>
      <div className="px-choices__grid">
        {options.map((option) => (
          <label className="px-choice" data-active={value === option.value} key={option.value}>
            <input
              checked={value === option.value}
              name={name}
              onChange={() => onChange(option.value)}
              type="radio"
            />
            <span className="px-choice__title">{option.title}</span>
            {option.description && <span className="px-choice__hint">{option.description}</span>}
          </label>
        ))}
      </div>
      {note && <p className="px-note">{note}</p>}
    </fieldset>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="px-field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {hint && <p className="px-note">{hint}</p>}
    </div>
  );
}

export function StatusPill({ tone, children }: { tone: "on" | "off" | "warn"; children: ReactNode }) {
  return (
    <span className="px-pill" data-tone={tone}>
      <span aria-hidden="true" className="px-pill__dot" />
      {children}
    </span>
  );
}
