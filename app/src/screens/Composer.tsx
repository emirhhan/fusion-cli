import { useState, type KeyboardEvent } from "react";
import { Button } from "../ui/Button";
import "./Composer.css";

interface ComposerProps {
  onAttach?: () => void;
  onCommand?: () => void;
  onSend: (task: string) => void;
  onStop?: () => void;
  onValueChange?: (value: string) => void;
  running?: boolean;
  value?: string;
}

export function Composer({
  onAttach = () => undefined,
  onCommand = () => undefined,
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
