import { useEffect, useRef, type KeyboardEvent } from "react";
import { Button } from "../ui/Button";
import type { PermissionKind, PermissionPromptPhase } from "./types";
import "./permissions.css";

interface PermissionPromptProps {
  canOpenSettings: boolean;
  error?: string | null;
  kind: PermissionKind;
  phase: PermissionPromptPhase;
  onContinue: () => void;
  onContinueToNext?: () => void;
  onDismiss?: () => void;
  onRetry: () => void;
  onOpenSettings: () => void;
}

const COPY: Record<PermissionKind, { title: string; explanation: string }> = {
  workspace: {
    title: "Çalışma klasörü erişimi",
    explanation: "Fusion'ın seçtiğiniz çalışma klasöründeki dosyaları göstermesi ve işlemesi için bu erişim gerekir.",
  },
  microphone: {
    title: "Mikrofon erişimi",
    explanation: "Fusion Talk'ın konuşmanızı dinleyebilmesi için mikrofon erişimi gerekir.",
  },
  speech: {
    title: "Konuşma tanıma erişimi",
    explanation: "Fusion Talk'ın söylediklerinizi metne çevirebilmesi için konuşma tanıma erişimi gerekir.",
  },
  keychain: {
    title: "Anahtarlık erişimi",
    explanation: "Sağlayıcı anahtarınızı güvenle kaydedebilmek için Anahtarlık erişimi gerekir.",
  },
};

export function PermissionPrompt({ canOpenSettings, error, kind, phase, onContinue, onContinueToNext, onDismiss, onRetry, onOpenSettings }: PermissionPromptProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const copy = COPY[kind];
  const denied = phase !== "preflight";
  const status = phase === "restricted"
    ? "Bu erişim bu Mac'te kısıtlanmış."
    : phase === "error"
      ? "İzin durumu doğrulanamadı."
      : `${copy.title} izni verilmedi.`;

  useEffect(() => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      if (restoreFocusRef.current?.isConnected) restoreFocusRef.current.focus();
    };
  }, []);

  useEffect(() => {
    dialogRef.current?.focus();
  }, [kind, phase]);

  const trapTab = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Tab") return;
    const actions = Array.from(actionsRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    if (!actions.length) return;
    const current = actions.indexOf(document.activeElement as HTMLButtonElement);
    if (current === -1) {
      event.preventDefault();
      actions[event.shiftKey ? actions.length - 1 : 0].focus();
      return;
    }
    if ((event.shiftKey && current === 0) || (!event.shiftKey && current === actions.length - 1)) {
      event.preventDefault();
      actions[event.shiftKey ? actions.length - 1 : 0].focus();
    }
  };

  return (
    <div className="permission-prompt__backdrop">
      <section
        aria-describedby="permission-prompt-description"
        aria-labelledby="permission-prompt-title"
        aria-modal="true"
        className="permission-prompt"
        onKeyDown={trapTab}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <p className="permission-prompt__eyebrow">İzin gerekiyor</p>
        <h2 id="permission-prompt-title">{copy.title}</h2>
        <p id="permission-prompt-description">{copy.explanation}</p>
        {denied && <p className="permission-prompt__status" role="status">{status}</p>}
        {error && <p className="permission-prompt__status" role="alert">{error}</p>}
        <div className="permission-prompt__actions" ref={actionsRef}>
          {denied ? (
            <>
              <Button onClick={onRetry} variant="primary">Yeniden dene</Button>
              {canOpenSettings && <Button onClick={onOpenSettings}>Sistem Ayarlarını Aç</Button>}
              {onContinueToNext && <Button onClick={onContinueToNext} variant="ghost">Sonraki izne geç</Button>}
              {onDismiss && <Button onClick={onDismiss} variant="ghost">Şimdi değil</Button>}
            </>
          ) : <>
            <Button onClick={onContinue} variant="primary">Devam et</Button>
            {onDismiss && <Button onClick={onDismiss} variant="ghost">Şimdi değil</Button>}
          </>}
        </div>
      </section>
    </div>
  );
}
