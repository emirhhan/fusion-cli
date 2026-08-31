import { useEffect, useRef } from "react";
import { Icon } from "../ui/Icon";
import "./NewTaskDialog.css";

interface NewTaskDialogProps {
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onChat: () => void;
  onFolder: () => void;
  open: boolean;
}

export function NewTaskDialog({
  busy = false,
  error = null,
  onCancel,
  onChat,
  onFolder,
  open,
}: NewTaskDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef(onCancel);
  const busyRef = useRef(busy);

  useEffect(() => { cancelRef.current = onCancel; }, [onCancel]);
  useEffect(() => { busyRef.current = busy; }, [busy]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        cancelRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const buttons = [...(dialogRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
      if (buttons.length === 0) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
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
  }, [open]);

  if (!open) return null;
  return (
    <div className="new-task-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onCancel();
    }}>
      <div
        aria-labelledby="new-task-title"
        aria-modal="true"
        className="new-task-dialog"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header>
          <span>Yeni çalışma</span>
          <h2 id="new-task-title">Yeni görev</h2>
          <p>Serbestçe sohbet et veya bilgisayarındaki bir klasörde çalış.</p>
        </header>
        <div className="new-task-dialog__choices">
          <button aria-label="Sohbet başlat" disabled={busy} onClick={onChat} type="button">
            <Icon name="new" size={20} />
            <span><strong>Sohbet başlat</strong><small>Dosya sistemine odaklanmadan tek yapay zekâyla konuş.</small></span>
          </button>
          <button aria-label="Klasörde kod görevi" disabled={busy} onClick={onFolder} type="button">
            <Icon name="files" size={20} />
            <span><strong>Klasörde kod görevi</strong><small>Masaüstü veya bilgisayarındaki herhangi bir proje klasörünü aç.</small></span>
          </button>
        </div>
        {error && <p aria-live="polite" className="new-task-dialog__error">{error}</p>}
        <footer>
          <button disabled={busy} onClick={onCancel} type="button">Vazgeç</button>
          {busy && <span aria-live="polite">Klasör seçiliyor…</span>}
        </footer>
      </div>
    </div>
  );
}
