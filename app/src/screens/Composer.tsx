import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { anmayiBul, anmayiDegistir } from "./dosyaAnmasi";
import { Button } from "../ui/Button";
import { MicIcon } from "../voice/MicIcon";
import "./Composer.css";
import { AttachmentChip } from "./AttachmentChip";
import { ModelPicker, type ModelOption } from "./ModelPicker";
import { ContextGauge } from "./ContextGauge";
import type { BaglamOlcusu } from "../protocol/types";

/**
 * Maliyet rozetinin görünür metni. Ölçü yoksa ya da `$0` ise `null` —
 * `ContextGauge`'daki "yanlış/gürültülü bir sıfır göstermek, hiç
 * göstermemekten kötüdür" ilkesiyle AYNI (bkz. o dosyanın yorumu): ücretsiz
 * modellerin çoğu turu tam olarak `$0` üretir, her seferinde basmak gürültüdür.
 */
/** Yolun son parçası. Liste dar; kullanıcı önce dosya adını arar. */
function dosyaAdi(yol: string): string {
  const parcalar = yol.split("/");
  return parcalar[parcalar.length - 1] || yol;
}

export function maliyetRozetMetni(costUsd: number | null): string | null {
  if (costUsd === null || costUsd <= 0) return null;
  return `$${costUsd.toFixed(costUsd < 0.01 ? 4 : 2)}`;
}

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

export interface DosyaOnerisi {
  yol: string;
  /** Eşleşen harflerin konumları; arayüz onları kalınlaştırır. */
  vurgu?: number[];
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
  /** Kalan bağlam ölçüsü; yoksa gösterge çizilmez. */
  context?: BaglamOlcusu | null;
  /** Oturumun toplam maliyeti (USD); yoksa ya da sıfırsa rozet çizilmez —
   *  çoğu ücretsiz model turu `$0` üretir, sıfırı her seferinde göstermek
   *  gürültüdür (bkz. `ContextGauge`'un "ölçü yoksa çizilmez" ilkesi). */
  costUsd?: number | null;
  onAttach?: () => void;
  onDropFiles?: (files: File[]) => void;
  /** `@` yazılınca aranacak sorgu. Verilmezse dosya anma kapalıdır. */
  onFileQuery?: (sorgu: string) => void;
  /** `onFileQuery` sonucunda gelen öneriler. */
  fileSuggestions?: DosyaOnerisi[];
  /** Konuşma kipini aç. Verilmezse mikrofon düğmesi çizilmez. */
  onVoice?: () => void;
  onRemoveAttachment?: (path: string) => void;
  onSend: (task: string) => void;
  /** Etkin ajan modeli. Boşsa seçici çizilmez. */
  activeModel?: string;
  /** Seçilebilir modeller; liste açılınca tembel yüklenir. */
  modelOptions?: ModelOption[];
  modelsBusy?: boolean;
  onModelMenuOpen?: () => void;
  onModelSelect?: (deger: string) => void;
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
  context = null,
  costUsd = null,
  onApprovalChange,
  onAttach = () => undefined,
  onDropFiles = () => undefined,
  onFileQuery,
  fileSuggestions = [],
  onVoice,
  onRemoveAttachment = () => undefined,
  onSend,
  onStop = () => undefined,
  onValueChange,
  running = false,
  activeModel = "",
  modelOptions = [],
  modelsBusy = false,
  onModelMenuOpen,
  onModelSelect,
  value,
}: ComposerProps) {
  const [internalValue, setInternalValue] = useState("");
  const [activeCommand, setActiveCommand] = useState(0);
  const [activeMention, setActiveMention] = useState(0);
  const [caret, setCaret] = useState(0);
  /** Kullanıcı Esc ile listeyi kapattı mı? Sorgu değişince kendiliğinden sıfırlanır. */
  const [mentionDismissed, setMentionDismissed] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const draft = value ?? internalValue;
  // İmleç metnin sonundan geride olabilir; anma imlecin ÖNÜNDEKİ parçaya bakar.
  const mention = onFileQuery ? anmayiBul(draft, Math.min(caret, draft.length)) : null;
  const mentionOpen = mention !== null && !mentionDismissed && fileSuggestions.length > 0;
  const filteredCommands = useMemo(() => {
    if (!draft.startsWith("/") || draft.includes("\n")) return [];
    const query = draft.slice(1).trim().toLocaleLowerCase("tr");
    return commands.filter((command) =>
      `${command.ad} ${command.aciklama} ${command.grup}`.toLocaleLowerCase("tr").includes(query),
    ).slice(0, 8);
  }, [commands, draft]);
  const paletteOpen = filteredCommands.length > 0;
  const mentionQuery = mention?.sorgu ?? null;
  useEffect(() => {
    // Anma kapalıyken sorgu gönderilmez: kapanır kapanmaz istek akışı da durur.
    if (mentionQuery === null) return;
    onFileQuery?.(mentionQuery);
    setActiveMention(0);
    // Sorgu değiştiyse kullanıcı yazmaya devam ediyor demektir: Esc ile
    // kapatılmış liste yeniden açılmalı.
    setMentionDismissed(false);
  }, [mentionQuery, onFileQuery]);
  const setDraft = (next: string, nextCaret?: number) => {
    if (value === undefined) setInternalValue(next);
    onValueChange?.(next);
    setActiveCommand(0);
    setCaret(nextCaret ?? next.length);
  };
  /** Seçilen yolu anmanın yerine koy ve imleci yolun ardına taşı. */
  const chooseMention = (yol: string) => {
    if (!mention) return;
    const sonuc = anmayiDegistir(draft, mention, Math.min(caret, draft.length), yol);
    setDraft(sonuc.metin, sonuc.imlec);
    // React değeri yazdıktan SONRA imleci koymak gerekiyor; aksi hâlde tarayıcı
    // imleci metnin sonuna atar ve kullanıcı cümlenin ortasına dönemez.
    requestAnimationFrame(() => {
      const alan = textareaRef.current;
      if (!alan) return;
      alan.focus();
      alan.setSelectionRange(sonuc.imlec, sonuc.imlec);
    });
  };
  const send = () => {
    const task = draft.trim();
    if (!task) return;
    setDraft("");
    onSend(task);
  };
  /** Sıradaki izin modu. Terminaldeki Shift+Tab döngüsüyle aynı sıra. */
  const nextApproval = (): ApprovalMode => {
    const index = APPROVAL_ORDER.indexOf(approval);
    return APPROVAL_ORDER[(index + 1) % APPROVAL_ORDER.length];
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Esc çalışan turu durdurur (Claude'daki davranış). Boş kutuda da çalışır;
    // kullanıcı durdurmak için fareye uzanmak zorunda kalmamalı.
    if (event.key === "Escape" && running) {
      event.preventDefault();
      onStop();
      return;
    }
    // IME adayını onaylayan Enter ve composition sırasında basılan diğer
    // kısayollar, Fusion komutu veya izin modu eylemi değildir.
    if (event.nativeEvent.isComposing) return;
    // Shift+Tab İZİN MODUNU döndürür — terminaldeki davranışın aynısı.
    // Sohbet/Kod ayrımı ayrı düğmelerdedir; ikisini aynı tuşa bindirmek
    // kullanıcının beklediği terminal alışkanlığını bozuyordu.
    if (event.key === "Tab" && event.shiftKey && onApprovalChange) {
      event.preventDefault();
      onApprovalChange(nextApproval());
      return;
    }
    // Anma paleti açıkken ok/Enter/Esc ONA aittir; komut paleti `/` ile
    // başlar ve ikisi aynı anda açılamaz, ama sıra yine de belirli olmalı.
    if (mentionOpen && event.key === "Escape") {
      event.preventDefault();
      setMentionDismissed(true);
      return;
    }
    if (mentionOpen && event.key === "ArrowDown") {
      event.preventDefault();
      setActiveMention((current) => (current + 1) % fileSuggestions.length);
      return;
    }
    if (mentionOpen && event.key === "ArrowUp") {
      event.preventDefault();
      setActiveMention((current) => (current - 1 + fileSuggestions.length) % fileSuggestions.length);
      return;
    }
    if (mentionOpen && (event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
      event.preventDefault();
      const secili = fileSuggestions[activeMention];
      if (secili) chooseMention(secili.yol);
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
      const normalizedDraft = draft.trim().toLocaleLowerCase("tr");
      const exactCommands = commands.filter(
        (command) => `/${command.ad}`.toLocaleLowerCase("tr") === normalizedDraft,
      );
      if (exactCommands.some((command) => command.destekleniyor)) {
        send();
        return;
      }
      if (exactCommands.length > 0) return;
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
        {mentionOpen && (
          <div aria-label="Dosya önerileri" className="composer__palette" role="listbox">
            {fileSuggestions.map((oneri, index) => (
              <button
                aria-label={oneri.yol}
                aria-selected={index === activeMention}
                key={oneri.yol}
                onClick={() => chooseMention(oneri.yol)}
                role="option"
                type="button"
              >
                <code>@{dosyaAdi(oneri.yol)}</code>
                <span>{oneri.yol}</span>
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
          onChange={(event) => setDraft(event.target.value, event.target.selectionStart)}
          onClick={(event) => setCaret(event.currentTarget.selectionStart)}
          onKeyDown={onKeyDown}
          onKeyUp={(event) => setCaret(event.currentTarget.selectionStart)}
          placeholder="Fusion'a bir görev ver"
          ref={textareaRef}
          rows={1}
          value={draft}
        />
        <div className="composer__toolbar">
          <div className="composer__tools">
            <span>
              <Button aria-label="Dosya veya klasör ekle" icon="attach" iconOnly onClick={onAttach} />
            </span>
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
            <span className="composer__actions">
              <ContextGauge olcu={context} />
              {maliyetRozetMetni(costUsd) && (
                <span className="composer__cost">{maliyetRozetMetni(costUsd)}</span>
              )}
              {/* Çalışırken de gönderilebilir: mesaj sıraya girer (bkz. useSessions). */}
              <Button
                aria-label="Sıraya ekle"
                disabled={!draft.trim()}
                icon="send"
                iconOnly
                onClick={send}
              />
              <Button aria-label="Durdur" icon="stop" iconOnly onClick={onStop} variant="primary" />
            </span>
          ) : (
            <span className="composer__actions">
              <ContextGauge olcu={context} />
              {maliyetRozetMetni(costUsd) && (
                <span className="composer__cost">{maliyetRozetMetni(costUsd)}</span>
              )}
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
              {onModelSelect && activeModel && (
                <ModelPicker
                  active={activeModel}
                  busy={modelsBusy}
                  onOpen={onModelMenuOpen}
                  onSelect={onModelSelect}
                  options={modelOptions}
                />
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
