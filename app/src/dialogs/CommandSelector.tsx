import { useEffect, useRef, useState } from "react";
import "./CommandSelector.css";

export interface CommandChoice {
  deger: string;
  etiket: string;
  aciklama: string;
}

export interface CommandSelectorPayload {
  adim: string;
  tur: "secim" | "metin" | "gizli_metin";
  baslik: string;
  secenekler: CommandChoice[];
  devam: { komut: string; arguman_on_eki: string };
  /** `saglayici`: API anahtarı adımında gelir; değer komut dizgesine katılmadan yapısal kaydedilir (S1-24). */
  serbest_metin: { gizli: boolean; yer_tutucu: string; saglayici?: string } | null;
}

interface CommandSelectorProps {
  busy: boolean;
  error?: string | null;
  onCancel: () => void;
  onSelect: (command: string) => void;
  /** Verilirse sağlayıcı anahtarı adımı değeri komut dizgesi yerine buraya gider (S1-24). */
  onSecret?: (provider: string, value: string) => void;
  open: boolean;
  selector: CommandSelectorPayload;
}

export function continuation(selector: CommandSelectorPayload, value: string): string {
  return `/${selector.devam.komut} ${selector.devam.arguman_on_eki}${value}`.trimEnd();
}

export function CommandSelector({
  busy,
  error = null,
  onCancel,
  onSelect,
  onSecret,
  open,
  selector,
}: CommandSelectorProps) {
  const [value, setValue] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  // busy/onCancel değişince efekt yeniden kurulmaz: yeniden kurulum yazılan değeri (parola/token)
  // siliyor ve odağı diyalogdan çıkarıyordu (U4-12). Güncel değerler ref'ten okunur.
  const busyRef = useRef(busy);
  const cancelRef = useRef(onCancel);
  useEffect(() => { busyRef.current = busy; }, [busy]);
  useEffect(() => { cancelRef.current = onCancel; }, [onCancel]);

  useEffect(() => {
    if (!open) return;
    setValue("");
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    queueMicrotask(() => dialogRef.current?.querySelector<HTMLElement>("button, input")?.focus());
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        cancelRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") ?? [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open, selector.adim]);

  if (!open) return null;
  const textStep = selector.tur !== "secim";
  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    const provider = selector.tur === "gizli_metin" ? selector.serbest_metin?.saglayici : undefined;
    // Gizli değer slash komut dizgesine girerse komut geçmişine/günlüğe düz metin düşebilir (S1-24).
    if (provider && onSecret) onSecret(provider, trimmed);
    else onSelect(continuation(selector, trimmed));
  };

  return (
    <div className="command-selector-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onCancel();
    }}>
      <div
        aria-labelledby="command-selector-title"
        aria-modal="true"
        className="command-selector"
        ref={dialogRef}
        role="dialog"
      >
        <header>
          <span>Fusion komutu</span>
          <h2 id="command-selector-title">{selector.baslik}</h2>
        </header>
        {textStep ? (
          <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <input
              autoComplete="off"
              disabled={busy}
              onChange={(event) => setValue(event.target.value)}
              placeholder={selector.serbest_metin?.yer_tutucu ?? "Değer"}
              type={selector.tur === "gizli_metin" ? "password" : "text"}
              value={value}
            />
            <button disabled={busy || !value.trim()} type="submit">Devam et</button>
          </form>
        ) : (
          <div className="command-selector__choices">
            {selector.secenekler.map((choice) => (
              <button
                disabled={busy}
                key={choice.deger}
                onClick={() => onSelect(continuation(selector, choice.deger))}
                type="button"
              >
                <strong>{choice.etiket}</strong>
                {choice.aciklama && <small>{choice.aciklama}</small>}
              </button>
            ))}
          </div>
        )}
        {error && <p aria-live="polite" className="command-selector__error">{error}</p>}
        <footer>
          <button disabled={busy} onClick={onCancel} type="button">Vazgeç</button>
          {busy && <span aria-live="polite">Uygulanıyor…</span>}
        </footer>
      </div>
    </div>
  );
}
