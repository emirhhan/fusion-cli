import { useMemo, useState, type DragEvent, type KeyboardEvent } from "react";
import { Button } from "../ui/Button";
import { MicIcon } from "../voice/MicIcon";
import "./Composer.css";
import { AttachmentChip } from "./AttachmentChip";

/** Çalışma kipi: sohbet kendiliğinden proje taramaz, kod proje köküne bağlıdır. */
export type WorkspaceMode = "sohbet" | "kod";

/** İzin modu — çekirdekteki `ApprovalMode` ile aynı değerler. */
export type ApprovalMode = "auto" | "plan" | "security";

/** Sıra, Shift+Tab'ın döneceği sıradır: terminaldeki davranışın aynısı. */
const APPROVAL_ORDER: ApprovalMode[] = ["auto", "plan", "security"];

const APPROVAL_LABEL: Record<ApprovalMode, string> = {
  auto: "Otomatik",
  plan: "Yalnız plan",
  security: "Güvenli mod",
};

const APPROVAL_HINT: Record<ApprovalMode, string> = {
  auto: "Fusion kendi ilerler, yıkıcı işlemde sorar.",
  plan: "Yalnız planlar; hiçbir şeyi değiştirmez.",
  security: "Her işlem için ayrı ayrı onay ister.",
};

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
  /** Seçili izin modu. Sabit metin BASILMAZ: kullanıcı security'ye geçtiğinde
   *  görev kutusunun altı da değişmeli — eskiden hep "Otomatik" yazıyordu. */
  approval?: ApprovalMode;
  /** Verilmezse mod salt okunur gösterilir. */
  onApprovalChange?: (mode: ApprovalMode) => void;
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
  approval = "auto",
  attachments = [],
  attachmentError = null,
  commands = [],
  mode = "sohbet",
  onApprovalChange,
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
  /** Sıradaki izin modu. Terminaldeki Shift+Tab döngüsüyle aynı sıra. */
  const nextApproval = (): ApprovalMode => {
    const index = APPROVAL_ORDER.indexOf(approval);
    return APPROVAL_ORDER[(index + 1) % APPROVAL_ORDER.length];
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Tab İZİN MODUNU döndürür — terminaldeki davranışın aynısı.
    // Sohbet/Kod ayrımı ayrı düğmelerdedir; ikisini aynı tuşa bindirmek
    // kullanıcının beklediği terminal alışkanlığını bozuyordu.
    if (event.key === "Tab" && event.shiftKey && onApprovalChange) {
      event.preventDefault();
      onApprovalChange(nextApproval());
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
              <AttachmentChip
                attachment={attachment}
                key={attachment.path}
                onRemove={() => onRemoveAttachment(attachment.path)}
              />
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
            {onApprovalChange ? (
              <button
                aria-label={`İzin modu: ${APPROVAL_LABEL[approval]}. Değiştirmek için tıkla ya da Shift+Tab.`}
                className="composer__approval"
                data-mode={approval}
                onClick={() => onApprovalChange(nextApproval())}
                title={APPROVAL_HINT[approval]}
                type="button"
              >
                {APPROVAL_LABEL[approval]}
              </button>
            ) : (
              <span className="composer__agent">{APPROVAL_LABEL[approval]}</span>
            )}
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
