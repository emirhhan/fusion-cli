import { useState, type KeyboardEvent } from "react";
import { Button } from "../ui/Button";
import "./Composer.css";

/** Çalışma kipi: sohbet kendiliğinden proje taramaz, kod proje köküne bağlıdır. */
export type WorkspaceMode = "sohbet" | "kod";

interface ComposerProps {
  mode?: WorkspaceMode;
  onAttach?: () => void;
  onCommand?: () => void;
  onModeChange?: (mode: WorkspaceMode) => void;
  onSend: (task: string) => void;
  onStop?: () => void;
  onValueChange?: (value: string) => void;
  running?: boolean;
  value?: string;
}

export function Composer({
  mode = "sohbet",
  onAttach = () => undefined,
  onCommand = () => undefined,
  onModeChange,
  onSend,
  onStop = () => undefined,
  onValueChange,
  running = false,
  value,
}: ComposerProps) {
  const [internalValue, setInternalValue] = useState("");
  const draft = value ?? internalValue;
  const setDraft = (next: string) => {
    if (value === undefined) setInternalValue(next);
    onValueChange?.(next);
  };
  const send = () => {
    const task = draft.trim();
    if (!task || running) return;
    setDraft("");
    onSend(task);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          aria-label="Mesaj"
          disabled={running}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Fusion'a bir görev ver"
          rows={1}
          value={draft}
        />
        <div className="composer__toolbar">
          <div className="composer__tools">
            {onModeChange && (
              <div aria-label="Çalışma kipi" className="composer__mode" role="group">
                {(["sohbet", "kod"] as const).map((item) => (
                  <button
                    aria-pressed={mode === item}
                    className="composer__mode-item"
                    key={item}
                    onClick={() => onModeChange(item)}
                    type="button"
                  >
                    {item === "sohbet" ? "Sohbet" : "Kod"}
                  </button>
                ))}
              </div>
            )}
            <Button aria-label="Dosya veya klasör ekle" icon="attach" iconOnly onClick={onAttach} />
            <Button aria-label="Komutlar" className="composer__command" onClick={onCommand} variant="ghost">
              /
            </Button>
            <span className="composer__mode">Agent · Otomatik</span>
          </div>
          {running ? (
            <Button aria-label="Durdur" icon="stop" iconOnly onClick={onStop} variant="primary" />
          ) : (
            <Button aria-label="Gönder" disabled={!draft.trim()} icon="send" iconOnly onClick={send} variant="primary" />
          )}
        </div>
      </div>
      <p className="composer__hint">Fusion hata yapabilir. Önemli değişiklikleri ve test kanıtlarını kontrol et.</p>
    </div>
  );
}
