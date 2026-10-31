import { submissionAccepted, type SubmissionResult } from "../sessions/submission";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import { anmayiBul, anmayiDegistir } from "./dosyaAnmasi";
import { Button } from "../ui/Button";
import { MicIcon } from "../voice/MicIcon";
import "./Composer.css";
import { AttachmentChip } from "./AttachmentChip";
import { ModelPicker, shortModelName, type ModelOption } from "./ModelPicker";
import {
  ApprovalModeMenu,
  approvalInfo,
  nextApprovalMode,
  type ApprovalMode,
} from "./ApprovalModeMenu";
import { ContextGauge } from "./ContextGauge";
import type { BaglamOlcusu } from "../protocol/types";
import type { WorkspaceMode } from "../sessions/useSessions";

/**
 * Maliyet rozetinin görünür metni. Ölçü yoksa ya da `$0` ise `null` —
 * `ContextGauge`'daki "yanlış/gürültülü bir sıfır göstermek, hiç
 * göstermemekten kötüdür" ilkesiyle AYNI (bkz. o dosyanın yorumu): ücretsiz
 * modellerin çoğu turu tam olarak `$0` üretir, her seferinde basmak gürültüdür.
 */
/** Yolun son parçası. Liste dar; kullanıcı önce dosya adını arar. */
function dosyaAdi(yol: string): string {
  // Windows yolları da `\` ile ayrılır (U1-19).
  const parcalar = yol.split(/[\\/]/);
  return parcalar[parcalar.length - 1] || yol;
}

export function maliyetRozetMetni(costUsd: number | null): string | null {
  if (costUsd === null || costUsd <= 0) return null;
  return `$${costUsd.toFixed(costUsd < 0.01 ? 4 : 2)}`;
}

export type { ApprovalMode } from "./ApprovalModeMenu";

const COMPACT_MESSAGE_CHARACTER_LIMIT = 90;

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

export interface McpSunucusu {
  ad: string;
  aciklama: string;
}

/** Kişilik seçicideki bir ajan (P-053): katalogdaki etkin ajanlar. */
export interface PersonaOption {
  ad: string;
  unvan?: string;
  aciklama?: string;
}

/** `@` listesindeki tek satır: MCP sunucusu ya da proje dosyası. */
interface AnmaOgesi {
  tur: "mcp" | "dosya";
  deger: string;
  aciklama: string;
}

export interface ComposerAttachment {
  kind: "file" | "image";
  name: string;
  path: string;
}

interface ComposerProps {
  workspaceMode?: WorkspaceMode;
  onWorkspaceModeChange?: (mode: WorkspaceMode) => void;
  /** Seçili izin modu. Sabit metin BASILMAZ: kullanıcı security'ye geçtiğinde
   *  görev kutusunun altı da değişmeli — eskiden hep "Otomatik" yazıyordu. */
  approval?: ApprovalMode;
  /** Verilmezse mod salt okunur gösterilir. */
  onApprovalChange?: (mode: ApprovalMode) => void;
  /** Oturum kişiliği (ajan adı) ya da null; `onPersonaChange` yoksa seçici çizilmez. */
  persona?: string | null;
  personaOptions?: PersonaOption[];
  onPersonaChange?: (persona: string | null) => void;
  attachments?: ComposerAttachment[];
  attachmentError?: string | null;
  commandError?: string | null;
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
  /** `@ad` ile bu tur için seçilebilen etkin MCP sunucuları. */
  mcpServers?: McpSunucusu[];
  /** Konuşma kipini aç. Verilmezse mikrofon düğmesi çizilmez. */
  onVoice?: () => void;
  /** Metni kutuya yazan dikte; konuşma kipinden ayrıdır. */
  onDictation?: () => void;
  dictating?: boolean;
  dictationError?: string | null;
  onRemoveAttachment?: (path: string) => void;
  onSend: (task: string) => SubmissionResult | Promise<SubmissionResult>;
  /** Etkin ajan modeli. Boşsa seçici çizilmez. */
  activeModel?: string;
  activeModelLabel?: string;
  /** Seçilebilir modeller; liste açılınca tembel yüklenir. */
  modelOptions?: ModelOption[];
  modelsError?: string;
  modelSelectionPending?: boolean;
  onModelConnect?: () => void;
  modelsBusy?: boolean;
  onModelMenuOpen?: () => void;
  onModelSelect?: (option: ModelOption) => void;
  onStop?: () => void;
  onValueChange?: (value: string) => void;
  running?: boolean;
  stopping?: boolean;
  busySubmissionMode?: "steer" | "queue";
  busySubmissionDisabled?: boolean;
  onBusySubmissionModeChange?: (mode: "steer" | "queue") => void;
  value?: string;
}

export function Composer({
  workspaceMode = "kod",
  onWorkspaceModeChange,
  approval = "auto",
  attachments = [],
  attachmentError = null,
  commandError = null,
  commands = [],
  context = null,
  costUsd = null,
  onApprovalChange,
  persona = null,
  personaOptions = [],
  onPersonaChange,
  onAttach = () => undefined,
  onDropFiles = () => undefined,
  onFileQuery,
  fileSuggestions = [],
  mcpServers = [],
  onVoice,
  onDictation,
  dictating = false,
  dictationError = null,
  onRemoveAttachment = () => undefined,
  onSend,
  onStop = () => undefined,
  stopping = false,
  busySubmissionMode = "steer",
  busySubmissionDisabled = false,
  onBusySubmissionModeChange,
  onValueChange,
  running = false,
  activeModel = "",
  activeModelLabel,
  modelOptions = [],
  modelsError = "",
  modelSelectionPending = false,
  onModelConnect,
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
  /** Gönderim reddedilirse/özel durum atarsa kullanıcıya gösterilen yerel hata (U1-05). */
  const [sendError, setSendError] = useState<string | null>(null);
  /** Desteklenmeyen komuta Enter basıldığında gösterilen ipucu (U1-06). */
  const [commandNotice, setCommandNotice] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingSubmission = useRef(false);
  const draft = value ?? internalValue;
  // Masaüstünde /subtask için görünür yol (P-054): komut sunucuda varsa ve taslak bir istemse.
  const subtaskAvailable = workspaceMode !== "sohbet" && !draft.trim().startsWith("/") && Boolean(draft.trim())
    && commands.some((command) => command.ad === "subtask" && command.destekleniyor);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  // Üst bileşen `onFileQuery` kimliğini her render'da değiştirebilir; efekt buna
  // bağlanırsa aynı sorgu yeniden istenir ve Esc ile kapatılan liste yeniden açılır.
  const onFileQueryRef = useRef(onFileQuery);
  onFileQueryRef.current = onFileQuery;
  const compactLayout = attachments.length === 0 && !attachmentError && !dictationError
    && !draft.includes("\n") && draft.length < COMPACT_MESSAGE_CHARACTER_LIMIT;
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const resize = () => {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    };
    resize();
    // Reflow when panels or the window change the available text width.
    if (typeof ResizeObserver === "undefined") return;
    let previousWidth = textarea.getBoundingClientRect().width;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry || entry.contentRect.width === previousWidth) return;
      previousWidth = entry.contentRect.width;
      resize();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [draft, compactLayout]);
  // İmleç metnin sonundan geride olabilir; anma imlecin ÖNÜNDEKİ parçaya bakar.
  const mention = onFileQuery ? anmayiBul(draft, Math.min(caret, draft.length)) : null;
  const mentionItems: AnmaOgesi[] = mention
    ? [
        ...mcpServers
          .filter((sunucu) => sunucu.ad.toLocaleLowerCase("tr").includes(mention.sorgu.toLocaleLowerCase("tr")))
          .map((sunucu) => ({ tur: "mcp" as const, deger: sunucu.ad, aciklama: `${sunucu.aciklama} · MCP` })),
        ...fileSuggestions.map((oneri) => ({ tur: "dosya" as const, deger: oneri.yol, aciklama: oneri.yol })),
      ]
    : [];
  const mentionOpen = mention !== null && !mentionDismissed && mentionItems.length > 0;
  // Öneriler eşzamansız gelip kısalabilir; eski indeks listenin dışına taşmasın.
  const mentionIndex = Math.min(activeMention, Math.max(mentionItems.length - 1, 0));
  const filteredCommands = useMemo(() => {
    if (!draft.startsWith("/") || draft.includes("\n")) return [];
    const query = draft.slice(1).trim().toLocaleLowerCase("tr");
    return commands.filter((command) =>
      `${command.ad} ${command.aciklama} ${command.grup}`.toLocaleLowerCase("tr").includes(query),
    ).slice(0, 8);
  }, [commands, draft]);
  const paletteOpen = filteredCommands.length > 0;
  const commandIndex = Math.min(activeCommand, Math.max(filteredCommands.length - 1, 0));
  const mentionQuery = mention?.sorgu ?? null;
  useEffect(() => {
    // Anma kapalıyken sorgu gönderilmez: kapanır kapanmaz istek akışı da durur.
    if (mentionQuery === null) return;
    onFileQueryRef.current?.(mentionQuery);
    setActiveMention(0);
    // Sorgu değiştiyse kullanıcı yazmaya devam ediyor demektir: Esc ile
    // kapatılmış liste yeniden açılmalı.
    setMentionDismissed(false);
  }, [mentionQuery]);
  const setDraft = (next: string, nextCaret?: number) => {
    if (value === undefined) setInternalValue(next);
    onValueChange?.(next);
    setActiveCommand(0);
    setSendError(null);
    setCommandNotice(null);
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
  const send = (prefix = "") => {
    const task = draft.trim() ? `${prefix}${draft.trim()}` : "";
    if (!task || pendingSubmission.current) return;
    const snapshot = draft;
    pendingSubmission.current = true;
    const fail = () => {
      pendingSubmission.current = false;
      setSendError("Mesaj gönderilemedi. Yeniden dene.");
    };
    const accept = (result: SubmissionResult) => {
      if (submissionAccepted(result)) {
        // Gönderim beklenirken yazılan ek karakterler korunur; yalnız gönderilen
        // kısım silinir. Aksi hâlde eski metin kutuda kalır ve çift gönderilir (U1-04).
        const current = draftRef.current;
        if (current === snapshot) setDraft("");
        else if (current.startsWith(snapshot)) setDraft(current.slice(snapshot.length).replace(/^\s+/, ""));
      }
      pendingSubmission.current = false;
    };
    try {
      const result = onSend(task);
      if (result instanceof Promise) result.then(accept, fail);
      else accept(result);
    } catch {
      fail();
    }
  };
  /** Sıradaki izin modu (Shift+Tab). "İzinleri atla" döngüde yoktur. */
  const nextApproval = (): ApprovalMode => nextApprovalMode(approval);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // IME adayını onaylayan Enter ve composition sırasında basılan diğer
    // kısayollar (aday penceresini kapatan Esc dahil), Fusion komutu, turu
    // durdurma veya izin modu eylemi değildir (U1-12).
    if (event.nativeEvent.isComposing) return;
    // Açık anma listesi Esc'i önce kendi kapatmak için tüketir (U1-13).
    if (mentionOpen && event.key === "Escape") {
      event.preventDefault();
      setMentionDismissed(true);
      return;
    }
    // Esc çalışan turu durdurur (Claude'daki davranış). Boş kutuda da çalışır;
    // kullanıcı durdurmak için fareye uzanmak zorunda kalmamalı.
    if (event.key === "Escape" && running && !stopping) {
      event.preventDefault();
      onStop();
      return;
    }
    // Shift+Tab İZİN MODUNU döndürür — terminaldeki davranışın aynısı.
    // Sohbet/Kod ayrımı ayrı düğmelerdedir; ikisini aynı tuşa bindirmek
    // kullanıcının beklediği terminal alışkanlığını bozuyordu.
    // Sohbet kipinde izin menüsü çizilmez: mod görünmeden değişmesin, Shift+Tab
    // de normal ters odak hareketini korusun (U1-03).
    const izinModuGorunur = !(workspaceMode === "sohbet" && onWorkspaceModeChange);
    if (event.key === "Tab" && event.shiftKey && onApprovalChange && izinModuGorunur) {
      event.preventDefault();
      onApprovalChange(nextApproval());
      return;
    }
    // Anma paleti açıkken ok/Enter/Esc ONA aittir; komut paleti `/` ile
    // başlar ve ikisi aynı anda açılamaz, ama sıra yine de belirli olmalı.
    if (mentionOpen && event.key === "ArrowDown") {
      event.preventDefault();
      setActiveMention((current) => (current + 1) % mentionItems.length);
      return;
    }
    if (mentionOpen && event.key === "ArrowUp") {
      event.preventDefault();
      setActiveMention((current) => (current - 1 + mentionItems.length) % mentionItems.length);
      return;
    }
    if (mentionOpen && (event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
      event.preventDefault();
      const secili = mentionItems[mentionIndex];
      if (secili) chooseMention(secili.deger);
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
      if (exactCommands.length > 0) {
        setCommandNotice(`/${exactCommands[0].ad} komutu uygulamada henüz desteklenmiyor.`);
        return;
      }
      const selected = filteredCommands[commandIndex];
      if (selected && draft.trim() !== `/${selected.ad}`) {
        if (selected.destekleniyor) setDraft(`/${selected.ad}`);
        else setCommandNotice(`/${selected.ad} komutu uygulamada henüz desteklenmiyor.`);
        return;
      }
      send();
    }
  };
  /** Yalnız dosya sürüklemeleri bu kutunun işi; metin bırakmayı textarea kendisi ele alır (U1-09). */
  const dosyaSurukleniyor = (event: DragEvent<HTMLDivElement>) =>
    [...(event.dataTransfer?.types ?? [])].includes("Files") || (event.dataTransfer?.files?.length ?? 0) > 0;
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!dosyaSurukleniyor(event)) return;
    event.preventDefault();
    const files = [...event.dataTransfer.files];
    if (files.length) onDropFiles(files);
  };
  /** Panodaki görsel/dosya (ekran görüntüsü) ek olarak eklenir; düz metin yapıştırma etkilenmez (U1-10). */
  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = [...(event.clipboardData?.files ?? [])];
    if (files.length === 0) return;
    event.preventDefault();
    onDropFiles(files);
  };

  return (
    <div className="composer-wrap">
      <div className="composer" data-busy-submission={running && !!onBusySubmissionModeChange ? "true" : undefined} data-layout={compactLayout ? "compact" : "expanded"} onDragOver={(event) => { if (dosyaSurukleniyor(event)) event.preventDefault(); }} onDrop={handleDrop}>
        {running && onBusySubmissionModeChange && <label className="composer__submission">
          <span>Bu mesaj</span>
          <select aria-label="Çalışan işe mesaj" value={busySubmissionMode} disabled={stopping || busySubmissionDisabled}
            onChange={(event) => onBusySubmissionModeChange(event.target.value as "steer" | "queue")}>
            <option value="steer">Çalışan işe talimat ekle</option>
            <option value="queue">Bağımsız işi sıraya al</option>
          </select>
        </label>}
        {stopping && <p className="composer__notice" role="status">İşlem durduruluyor; açık işlemler kapatılıyor.</p>}
        {paletteOpen && (
          <div aria-label="Komut önerileri" className="composer__palette" id="composer-komut-listesi" role="listbox">
            {filteredCommands.map((command, index) => (
              <button
                aria-label={`${command.ad} — ${command.aciklama}`}
                aria-selected={index === commandIndex}
                disabled={!command.destekleniyor}
                id={`composer-komut-${index}`}
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
          <div aria-label="Anma önerileri" className="composer__palette" id="composer-anma-listesi" role="listbox">
            {mentionItems.map((oge, index) => (
              <button
                aria-label={oge.tur === "mcp" ? `MCP ${oge.deger}` : oge.deger}
                aria-selected={index === mentionIndex}
                id={`composer-anma-${index}`}
                key={`${oge.tur}:${oge.deger}`}
                onClick={() => chooseMention(oge.deger)}
                role="option"
                type="button"
              >
                <code>@{oge.tur === "mcp" ? oge.deger : dosyaAdi(oge.deger)}</code>
                <span>{oge.aciklama}</span>
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
        {[attachmentError, dictationError, commandError, commandNotice, sendError].map((error, index) => error && <p key={index} className="composer__attachment-error" role="alert">{error}</p>)}
        <textarea
          aria-label="Mesaj"
          {...(paletteOpen || mentionOpen
            ? {
                "aria-activedescendant": paletteOpen ? `composer-komut-${commandIndex}` : `composer-anma-${mentionIndex}`,
                "aria-autocomplete": "list" as const,
                "aria-controls": paletteOpen ? "composer-komut-listesi" : "composer-anma-listesi",
                "aria-haspopup": "listbox" as const,
              }
            : {})}
          onChange={(event) => setDraft(event.target.value, event.target.selectionStart)}
          onClick={(event) => setCaret(event.currentTarget.selectionStart)}
          onKeyDown={onKeyDown}
          onKeyUp={(event) => setCaret(event.currentTarget.selectionStart)}
          onPaste={handlePaste}
          placeholder="İstediğin bir şeyi sor"
          ref={textareaRef}
          rows={1}
          value={draft}
        />
        <div className="composer__toolbar">
          <div className="composer__tools">
            <span>
              <Button aria-label="Dosya veya klasör ekle" icon="attach" iconOnly onClick={onAttach} />
            </span>
            {onWorkspaceModeChange && (
              <button
                aria-label={`Çalışma kipi: ${workspaceMode === "sohbet" ? "Sohbet" : "Çalışma"}. Değiştirmek için tıkla.`}
                className="composer__mode"
                onClick={() => onWorkspaceModeChange(workspaceMode === "sohbet" ? "kod" : "sohbet")}
                title={workspaceMode === "sohbet" ? "Gündelik sorular ve fikirler" : "Dosya, terminal ve araçlarla çalışma"}
                type="button"
              >
                {workspaceMode === "sohbet" ? "Sohbet" : "Çalışma"}
              </button>
            )}
            {workspaceMode === "sohbet" && onWorkspaceModeChange ? null : onApprovalChange ? (
              <ApprovalModeMenu mode={approval} onChange={onApprovalChange} />
            ) : (
              <span className="composer__agent">{approvalInfo(approval).label}</span>
            )}
            {onPersonaChange && workspaceMode !== "sohbet" && (
              <select
                aria-label="Oturum kişiliği"
                className="composer__persona"
                data-active={persona ? "true" : undefined}
                onChange={(event) => onPersonaChange(event.target.value || null)}
                title="Oturumu bir ajan tanımıyla sür (explore, plan…); boş = varsayılan Fusion"
                value={persona ?? ""}
              >
                <option value="">Kişilik yok</option>
                {personaOptions.map((option) => (
                  <option key={option.ad} title={option.aciklama} value={option.ad}>{option.unvan && option.unvan !== option.ad ? `${option.unvan} (${option.ad})` : option.ad}</option>
                ))}
                {persona && !personaOptions.some((option) => option.ad === persona) && <option value={persona}>{persona}</option>}
              </select>
            )}
          </div>
          {running ? (
            <span className="composer__actions">
              {onModelSelect && <ModelPicker active={activeModel} activeLabel={activeModelLabel ? `${activeModelLabel} · sonraki tur` : `${shortModelName(activeModel)} · sonraki tur`} options={modelOptions} busy={modelsBusy} pending={modelSelectionPending} error={modelsError} onOpen={onModelMenuOpen} onRetry={onModelMenuOpen} onConnect={onModelConnect} onSelect={onModelSelect} />}
              {/* Çalışırken "Bağlamı sıkıştır" sunulmaz: onSend çalışan tura talimat/sıra olarak gider
                  ve /compact komut yerine modele metin olarak iletilebilirdi (U1-11). */}
              <ContextGauge olcu={context} />
              {maliyetRozetMetni(costUsd) && (
                <span className="composer__cost">{maliyetRozetMetni(costUsd)}</span>
              )}
              {/* Çalışırken de gönderilebilir: mesaj sıraya girer (bkz. useSessions).
                  Düğme yalnız yazı varken çıkar; boşken soluk bir ok "gönder
                  çalışmıyor" gibi okunuyordu. */}
              {draft.trim() && (
                <Button aria-label="Sıraya ekle" icon="send" iconOnly onClick={() => send()} />
              )}
              {/* ChatGPT'deki gibi: tur sürerken ses düğmelerinin yerinde beyaz
                  yuvarlak içinde kare durdur düğmesi — Fusion'ın çalıştığı buradan anlaşılır. */}
              <button aria-label={stopping ? "Durduruluyor" : "Durdur"} disabled={stopping} className="composer__stop" onClick={onStop} title={stopping ? "Açık işlemler kapatılıyor" : "Durdur (Esc)"} type="button">
                <span aria-hidden="true" className="composer__stop-square" />
              </button>
            </span>
          ) : (
            <span className="composer__actions">
              <ContextGauge olcu={context} onCompact={() => onSend("/compact")} />
              {maliyetRozetMetni(costUsd) && (
                <span className="composer__cost">{maliyetRozetMetni(costUsd)}</span>
              )}
              {onDictation && (
                <button
                  aria-label={dictating ? "Dikteyi durdur" : "Dikte et"}
                  aria-pressed={dictating}
                  className="composer__voice"
                  data-listening={dictating}
                  onClick={onDictation}
                  type="button"
                >
                  <MicIcon size={18} />
                </button>
              )}
              {onVoice && (
                <button aria-label="Sesli konuşmayı aç" className="composer__voice composer__voice--conversation" onClick={onVoice} type="button">
                  <svg aria-hidden="true" fill="none" height="18" stroke="currentColor" strokeLinecap="round" strokeWidth="2" viewBox="0 0 24 24" width="18"><path d="M3 10v4M7 6v12M11 3v18M15 7v10M19 5v14M23 10v4" /></svg>
                </button>
              )}
              {onModelSelect && (
                <ModelPicker
                  active={activeModel}
                  activeLabel={activeModelLabel}
                  busy={modelsBusy}
                  pending={modelSelectionPending}
                  error={modelsError}
                  onRetry={onModelMenuOpen}
                  onConnect={onModelConnect}
                  onOpen={onModelMenuOpen}
                  onSelect={onModelSelect}
                  options={modelOptions}
                />
              )}
              {subtaskAvailable && (
                <button
                  aria-label="Alt görev olarak gönder"
                  className="composer__subtask"
                  onClick={() => send("/subtask ")}
                  title="Bağlamı devralan bir alt ajanda çalıştır; sohbete yalnız özeti döner (/subtask)"
                  type="button"
                >
                  Alt görev
                </button>
              )}
              <Button aria-label="Gönder" disabled={!draft.trim()} icon="send" iconOnly onClick={() => send()} variant="primary" />
            </span>
          )}
        </div>
      </div>
      {/* ChatGPT'deki gibi uyarı composer'ın altında durur; konuşmayı bölmez. */}
      <p className="composer__disclaimer">Fusion hata yapabilir. Önemli değişiklikleri ve test kanıtlarını kontrol et.</p>
    </div>
  );
}
