import { useEffect, useRef } from "react";
import { Button } from "../ui/Button";
import type { PermissionKind, PermissionPromptPhase } from "./types";
import "./permissions.css";

interface PermissionPromptProps {
  kind: PermissionKind;
  phase: PermissionPromptPhase;
  onContinue: () => void;
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

export function PermissionPrompt({ kind, phase, onContinue, onRetry, onOpenSettings }: PermissionPromptProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const copy = COPY[kind];
  const denied = phase !== "preflight";
  const status = phase === "restricted" ? "Bu erişim bu Mac'te kısıtlanmış." : `${copy.title} izni verilmedi.`;

  useEffect(() => {
    dialogRef.current?.focus();
  }, [kind, phase]);

  return (
    <div className="permission-prompt__backdrop">
      <section
        aria-describedby="permission-prompt-description"
        aria-labelledby="permission-prompt-title"
        aria-modal="true"
        className="permission-prompt"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <p className="permission-prompt__eyebrow">İzin gerekiyor</p>
        <h2 id="permission-prompt-title">{copy.title}</h2>
        <p id="permission-prompt-description">{copy.explanation}</p>
        {denied && <p className="permission-prompt__status" role="status">{status}</p>}
        <div className="permission-prompt__actions">
          {denied ? (
            <>
              <Button onClick={onRetry} variant="primary">Yeniden dene</Button>
              <Button onClick={onOpenSettings}>Sistem Ayarlarını Aç</Button>
            </>
          ) : <Button onClick={onContinue} variant="primary">Devam et</Button>}
        </div>
      </section>
    </div>
  );
}
