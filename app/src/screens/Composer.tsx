import { useMemo, useState, type DragEvent, type KeyboardEvent } from "react";
import { Button } from "../ui/Button";
import { MicIcon } from "../voice/MicIcon";
import "./Composer.css";

/** Çalışma kipi: sohbet kendiliğinden proje taramaz, kod proje köküne bağlıdır. */
export type WorkspaceMode = "sohbet" | "kod";

export interface ComposerCommand {
  ad: string;
  aciklama: string;
  grup: string;
  kullanim: string;
  destekleniyor: boolean;
}

export interface ComposerAttachment {
  kind: "file" | "image";
  name: string;
  path: string;
}

interface ComposerProps {
  attachments?: ComposerAttachment[];
  attachmentError?: string | null;
  commands?: ComposerCommand[];
  mode?: WorkspaceMode;
  onAttach?: () => void;
  onDropFiles?: (files: File[]) => void;
  onModeChange?: (mode: WorkspaceMode) => void;
  /** Konuşma kipini aç. Verilmezse mikrofon düğmesi çizilmez. */
  onVoice?: () => void;
  onRemoveAttachment?: (path: string) => void;
  onSend: (task: string) => void;
  onStop?: () => void;
  onValueChange?: (value: string) => void;
  running?: boolean;
  value?: string;
}

export function Composer({
  attachments = [],
  attachmentError = null,
  commands = [],
  mode = "sohbet",
  onAttach = () => undefined,
  onDropFiles = () => undefined,
  onModeChange,
  onVoice,
  onRemoveAttachment = () => undefined,
  onSend,
  onStop = () => undefined,
  onValueChange,
  running = false,
  value,
}: ComposerProps) {
  const [internalValue, setInternalValue] = useState("");
  const [activeCommand, setActiveCommand] = useState(0);
  const draft = value ?? internalValue;
  const filteredCommands = useMemo(() => {
    if (!draft.startsWith("/") || draft.includes("\n")) return [];
    const query = draft.slice(1).trim().toLocaleLowerCase("tr");
    return commands.filter((command) =>
      `${command.ad} ${command.aciklama} ${command.grup}`.toLocaleLowerCase("tr").includes(query),
    ).slice(0, 8);
  }, [commands, draft]);
  const paletteOpen = filteredCommands.length > 0;
  const setDraft = (next: string) => {
    if (value === undefined) setInternalValue(next);
    onValueChange?.(next);
    setActiveCommand(0);
  };
  const send = () => {
    const task = draft.trim();
    if (!task || running) return;
    setDraft("");
    onSend(task);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Tab" && event.shiftKey && onModeChange) {
      event.preventDefault();
      onModeChange(mode === "sohbet" ? "kod" : "sohbet");
      return;
    }
    if (paletteOpen && event.key === "ArrowDown") {
      event.preventDefault();
      setActiveCommand((current) => (current + 1) % filteredCommands.length);
      return;
    }
    if (paletteOpen && event.key === "ArrowUp") {
      event.preventDefault();
      setActiveCommand((current) => (current - 1 + filteredCommands.length) % filteredCommands.length);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      const selected = filteredCommands[activeCommand];
      if (selected && draft.trim() !== `/${selected.ad}`) {
        setDraft(`/${selected.ad}`);
        return;
      }
      send();
    }
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const files = [...event.dataTransfer.files];
    if (files.length) onDropFiles(files);
  };

  return (
    <div className="composer-wrap">
      <div className="composer" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
        {paletteOpen && (
          <div aria-label="Komut önerileri" className="composer__palette" role="listbox">
            {filteredCommands.map((command, index) => (
              <button
                aria-label={`${command.ad} — ${command.aciklama}`}
                aria-selected={index === activeCommand}
                disabled={!command.destekleniyor}
                key={`${command.grup}:${command.ad}`}
                onClick={() => setDraft(`/${command.ad}`)}
                role="option"
                title={command.destekleniyor ? undefined : "Bu komut uygulamada henüz desteklenmiyor"}
                type="button"
              >
                <code>/{command.ad}</code>
                <span>{command.aciklama}</span>
                <small>{command.grup}</small>
              </button>
            ))}
          </div>
        )}
        {attachments.length > 0 && (
          <div aria-label="Ekler" className="composer__attachments">
            {attachments.map((attachment) => (
              <span className="composer__attachment" key={attachment.path}>
                <span aria-hidden="true">{attachment.kind === "image" ? "▧" : "▤"}</span>
                <span>{attachment.name}</span>
                <button
                  aria-label={`${attachment.name} ekini kaldır`}
                  onClick={() => onRemoveAttachment(attachment.path)}
                  type="button"
                >×</button>
              </span>
            ))}
          </div>
        )}
        {attachmentError && <p aria-live="polite" className="composer__attachment-error">{attachmentError}</p>}
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
            <span className="composer__agent">Agent · Otomatik</span>
          </div>
          {running ? (
            <Button aria-label="Durdur" icon="stop" iconOnly onClick={onStop} variant="primary" />
          ) : (
            <span className="composer__actions">
              {onVoice && (
                <button
                  aria-label="Konuşarak anlat"
                  className="composer__voice"
                  onClick={onVoice}
                  type="button"
                >
                  <MicIcon size={18} />
                </button>
              )}
              <Button aria-label="Gönder" disabled={!draft.trim()} icon="send" iconOnly onClick={send} variant="primary" />
            </span>
          )}
        </div>
      </div>
      <p className="composer__hint">Fusion hata yapabilir. Önemli değişiklikleri ve test kanıtlarını kontrol et.</p>
    </div>
  );
}
