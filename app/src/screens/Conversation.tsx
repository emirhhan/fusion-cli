import { useMemo, useRef, useState, type ReactNode } from "react";

import { DeliveryCard } from "./DeliveryCard";
import type { DeliveryEvidence } from "../protocol/deliveryEvidence";

import { Button } from "../ui/Button";
import "./Conversation.css";

import type { OlayAdimi } from "../protocol/olayMetni";
import { assetUrl } from "../platform/assetUrl";
import { Markdown } from "../markdown/Markdown";
import { DiffCard } from "../markdown/DiffCard";
import { ActivityLine, activityState } from "./ActivityLine";
import { ChangeSummary, turnChanges } from "./ChangeSummary";
import { AgentActivity } from "./AgentActivity";
import type { AjanKarti } from "../team/ekipOlaylari";
import { PreviewCard } from "./PreviewCard";
import { ImageGenerationCard } from "./ImageGenerationCard";
import { isImageCommand, parseImageRequest } from "./capabilityInput";
import { useStickToBottom } from "./useStickToBottom";

export interface MesajEki {
  kind: "image" | "file";
  name: string;
  path: string;
}

/** Tur sonunda gösterilen tek takip önerisi. */
export interface TakipOnerisi {
  /** Rozette yazan kısa metin. */
  etiket: string;
  /** Tıklanınca gönderilecek tam görev. */
  gorev: string;
}

/** Canlı görev listesindeki tek madde. */
export interface GorevMaddesi {
  durum: "bekliyor" | "yapiliyor" | "bitti";
  metin: string;
}

export interface Mesaj {
  id?: string;
  submissionId?: string;
  delivery?: DeliveryEvidence;
  metin: string;
  rol: "kullanici" | "asistan" | "olay" | "degisiklik" | "gorevler" | "oneriler" | "ekip" | "onizleme";
  /** Yalnız `rol === "onizleme"` için: ajanın çalıştırdığı sitenin adresi. */
  onizleme?: { url: string; baslik?: string; tur?: string };
  /** Yalnız `rol === "olay"` için: blokta toplanan adımlar. */
  adimlar?: OlayAdimi[];
  /** Yalnız `rol === "olay"` için: bloğun İLK adımının başladığı `Date.now()`.
   *  Süre sayacı bu SABİT zamandan hesaplanır (bkz. `ActivityLine`) — mesaj
   *  oturum durumunda tutulduğu için sekme değişip geri dönünce ya da
   *  bileşen yeniden bağlanınca sıfırlanmaz. */
  baslangicZamani?: number;
  /** Gerçek tur bitiş damgası; eski kayıtlarda bulunmayabilir. */
  bitisZamani?: number;
  /** Turun şimdiye dek ürettiği çıktı token'ı; sağlayıcı bildirmediyse yok. */
  tokenSayisi?: number;
  /** Kullanıcının o mesajla birlikte gönderdiği ekler. */
  ekler?: MesajEki[];
  /** Yalnız `rol === "degisiklik"` için: dosyaya uygulanan unified diff. */
  diff?: string;
  /** Model hâlâ yazıyor: balon geçicidir, tur bitince nihai cevap gelir. */
  akan?: boolean;
  /** Araç adımlarının arasındaki kısa ara anlatım; nihai cevap değildir. */
  ara?: boolean;
  /** Yalnız `rol === "gorevler"` için: modelin güncel görev listesi. */
  gorevler?: GorevMaddesi[];
  /** Yalnız `rol === "oneriler"` için: turun kanıtından türeyen sonraki adımlar. */
  oneriler?: TakipOnerisi[];
  /** Tur hatayla bitti: yanıtın altında "Hatayı bildir" sunulur. */
  hata?: boolean;
  /** Yalnız `rol === "ekip"` için: bu grupta koşan alt ajan kartları. */
  ajanlar?: AjanKarti[];
  /** Yalnız `rol === "ekip"` için: aynı anda başlatılan ajan sayısı. */
  grupBoyutu?: number;
}

/**
 * Gönderilmiş eklerin dökümü.
 *
 * Ek gönderildikten sonra composer'dan siliniyordu ve geçmişte hiçbir izi
 * kalmıyordu: kullanıcı hangi görseli gönderdiğini göremiyordu. Görseller
 * küçük önizlemeyle, diğer dosyalar adıyla durur.
 */
function SentAttachments({ ekler, onOpenFile }: { ekler: MesajEki[]; onOpenFile?: (path: string) => void }) {
  return (
    <div aria-label="Gönderilen ekler" className="conversation__attachments">
      {ekler.map((ek) => {
        const kaynak = ek.kind === "image" ? assetUrl(ek.path) : null;
        const content = <>
          {kaynak ? <img alt={`${ek.name} önizlemesi`} height={44} src={kaynak} width={44} />
            : <span aria-hidden="true">▤</span>}
          <span className="conversation__attachment-name">{ek.name}</span>
        </>;
        return onOpenFile ? (
          <Button variant="ghost" className="conversation__attachment" key={ek.path}
            aria-label={`${ek.name} dosyasını aç`} title={ek.path} onClick={() => onOpenFile(ek.path)}>
            {content}
          </Button>
        ) : <span className="conversation__attachment" key={ek.path} title={ek.path}>{content}</span>;
      })}
    </div>
  );
}

/**
 * Fusion'ın cevabı.
 *
 * Metin MARKDOWN olarak çizilir. Eskiden düz metindi ve model kod yazdığında
 * cevap okunmaz bir duvara dönüşüyordu: başlıklar, listeler ve kod blokları
 * ham işaretleriyle akıyordu. Kod artık kendi kartında, katlanmış durur.
 */
/** Başarısız tur yanıtı: çekirdek `ok=false` döndürdü ya da istek hiç tamamlanmadı. */
export function hataMesajiMi(message: Mesaj): boolean {
  return message.rol === "asistan" && (message.hata === true || message.metin.startsWith("Hata:"));
}

function AssistantMessage({ text, onOpenFile, onReport, onReadAloud, onEvaluate, onContinue, ara = false, children }: {
  text: string;
  children?: ReactNode;
  onReadAloud?: () => Promise<void> | void;
  onEvaluate?: (rating: "positive" | "negative") => Promise<void> | void;
  onContinue?: () => Promise<void> | void;
  /** Adımlar arasındaki ara anlatım: Claude'daki gibi düz metin, eylem satırı yok. */
  ara?: boolean;
  onOpenFile?: (path: string) => void;
  /** Verilirse yanıtın altında "Hatayı bildir" düğmesi çıkar. */
  onReport?: () => void;
}) {
  const [copyState, setCopyState] = useState<string | null>(null);
  const copyPending = useRef(false);
  const [evaluationOpen, setEvaluationOpen] = useState(false);
  const [rating, setRating] = useState<"positive" | "negative" | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const actionLock = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const perform = async (callback: () => Promise<void> | void, success?: () => void) => {
    if (actionLock.current) return;
    actionLock.current = true;
    setActionPending(true);
    setActionError(null);
    setActionStatus(null);
    try { await callback(); success?.(); }
    catch (reason) { setActionError(reason instanceof Error ? reason.message : String(reason)); }
    finally { actionLock.current = false; setActionPending(false); }
  };
  const copy = async () => {
    if (copyPending.current) return;
    if (!navigator.clipboard?.writeText) { setCopyState("Panoya erişilemiyor. Metni seçip manuel kopyala."); return; }
    copyPending.current = true;
    setCopyState("Kopyalanıyor…");
    try { await navigator.clipboard.writeText(text); setCopyState("Kopyalandı"); }
    catch (reason) { setCopyState(`Kopyalanamadı: ${reason instanceof Error ? reason.message : String(reason)}`); }
    finally { copyPending.current = false; }
  };
  return (
    <article aria-label="Fusion yanıtı" className="conversation__article">
      <div className="conversation__role">Fusion</div>
      <div className="conversation__text">
        <Markdown onOpenFile={onOpenFile} text={text} />
      </div>
      {children}
      {!ara && <div className="conversation__actions">
        <Button aria-label="Yanıtı kopyala" icon="copy" iconOnly disabled={copyPending.current} onClick={() => void copy()} />
        {onReadAloud && <Button aria-label="Sesli oku" title="Sesli oku" icon="speaker" iconOnly disabled={actionPending} onClick={() => void perform(onReadAloud)} />}
        {onEvaluate && <div className="conversation__evaluation">
          <Button aria-label="Yanıtı değerlendir" title="Yanıtı değerlendir" aria-expanded={evaluationOpen} icon="thumbsUp" iconOnly onClick={() => setEvaluationOpen(!evaluationOpen)} />
          {evaluationOpen && <div role="group" aria-label="Yanıt değerlendirmesi" className="conversation__rating" onKeyDown={(event) => { if (event.key === "Escape") { setEvaluationOpen(false); event.currentTarget.parentElement?.querySelector<HTMLButtonElement>("button")?.focus(); } }}>
            {(["positive", "negative"] as const).map((value) => <Button key={value} aria-label={value === "positive" ? "Olumlu değerlendir" : "Olumsuz değerlendir"} aria-pressed={rating === value} icon={value === "positive" ? "thumbsUp" : "thumbsDown"} iconOnly disabled={actionPending} onClick={() => void perform(() => onEvaluate(value), () => { setRating(value); setEvaluationOpen(false); setActionStatus("Değerlendirmen kaydedildi"); })} />)}
          </div>}
        </div>}
        {onContinue && <Button aria-label="Yeni sohbette devam et" title="Yeni sohbette devam et" icon="branch" iconOnly disabled={actionPending} onClick={() => void perform(onContinue)} />}
        {copyState && <span role="status">{copyState}</span>}
        {actionStatus && <span role="status">{actionStatus}</span>}
        {actionError && <span role="alert">{actionError}</span>}
        {onReport && (
          <button className="conversation__report" onClick={onReport} type="button">
            Hatayı bildir
          </button>
        )}
      </div>}
    </article>
  );
}

/**
 * Modelin güncel görev listesi.
 *
 * Claude'daki canlı plan kartının karşılığı: kullanıcı işin neresinde olunduğunu
 * tek bakışta görür. Liste akışta TEK kart olarak durur (bkz. `olayAkisi`).
 */
function TaskList({ gorevler }: { gorevler: GorevMaddesi[] }) {
  const bitti = gorevler.filter((gorev) => gorev.durum === "bitti").length;
  return (
    <section aria-label="Görev listesi" className="conversation__tasks">
      <header>
        Görevler <span>{bitti}/{gorevler.length}</span>
      </header>
      <ul>
        {gorevler.map((gorev) => (
          <li data-durum={gorev.durum} key={gorev.metin}>
            <span aria-hidden="true">{gorev.durum === "bitti" ? "✓" : gorev.durum === "yapiliyor" ? "▶" : "○"}</span>
            {gorev.metin}
          </li>
        ))}
      </ul>
    </section>
  );
}

export interface ConversationProps {
  mesajlar: Mesaj[];
  onReadAloud?: (text: string) => Promise<void> | void;
  onEvaluate?: (text: string, rating: "positive" | "negative") => Promise<void> | void;
  onContinueInNewChat?: (messageIndex: number) => Promise<void> | void;
  /** Çekirdeğin gerçek tur durumu; iptalden sonra eski olayın saati işlemez. */
  running?: boolean;
  /** Kod kartındaki dosya adına tıklanınca çağrılır; çalışma paneli o dosyayı açar. */
  onOpenFile?: (path: string) => void;
  /** Ayarlardaki "adımları göster" tercihi. */
  showSteps?: boolean;
  /** Takip önerisine tıklanınca çağrılır. Verilmezse rozetler çizilmez. */
  onOneriSec?: (gorev: string) => void;
  /** Başarısız yanıtın "Hatayı bildir" düğmesi. Verilmezse düğme çizilmez. */
  onHataBildir?: (metin: string) => void;
  onRetrySubmission?: (requestId: string) => void;
  /** Önizleme kartındaki "Uygulamada aç"; verilmezse yalnız bağlantı gösterilir. */
  onOpenPreview?: (url: string) => void;
}

interface WorkEntry { message: Mesaj; index: number }
interface WorkGroup { entries: WorkEntry[]; work: boolean; completed: boolean; turn: Mesaj[] }

function isWork(message: Mesaj): boolean {
  return ["olay", "ekip", "gorevler"].includes(message.rol)
    || (message.rol === "asistan" && (message.ara === true || message.akan === true) && !hataMesajiMi(message));
}

/** Görsel gruplama özgün mesaj indislerini ve model geçmişini korur. */
function workGroups(messages: Mesaj[], running: boolean): WorkGroup[] {
  const groups: WorkGroup[] = [];
  let start = 0;
  while (start < messages.length) {
    let end = start + 1;
    while (end < messages.length && messages[end].rol !== "kullanici") end++;
    const turn = messages.slice(start, end);
    const completed = !(running && end === messages.length) && turn.some(message => message.rol === "asistan" && !message.ara && !message.akan);
    let work: WorkGroup | undefined;
    for (let index = start; index < end; index++) {
      const message = messages[index];
      if (isWork(message)) {
        const previous = messages[index - 1];
        if (message.ara && previous?.ara && !hataMesajiMi(previous) && previous.metin === message.metin) continue;
        if (!work) { work = { entries: [], work: true, completed, turn }; groups.push(work); }
        work.entries.push({message, index});
      } else { groups.push({entries: [{message, index}], work: false, completed, turn}); }
    }
    start = end;
  }
  return groups;
}

function workDuration(messages: Mesaj[]): string {
  const starts = messages.flatMap(message => message.baslangicZamani === undefined ? [] : [message.baslangicZamani]);
  const ends = messages.flatMap(message => message.bitisZamani === undefined ? [] : [message.bitisZamani]);
  if (!starts.length || !ends.length) return "Çalışma geçmişi";
  const seconds = Math.floor((Math.max(...ends) - Math.min(...starts)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "Çalışma geçmişi";
  return `${seconds >= 60 ? `${Math.floor(seconds / 60)}d ` : ""}${seconds % 60}sn çalıştı`;
}

export function Conversation({
  mesajlar,
  onReadAloud,
  onEvaluate,
  onContinueInNewChat,
  onOpenFile,
  onOneriSec,
  onHataBildir,
  onRetrySubmission,
  onOpenPreview,
  running = true,
  showSteps = false,
}: ConversationProps) {
  const sonOlay = [...mesajlar].reverse().find((message) => message.rol === "olay");
  const sonDurum = sonOlay ? activityState(sonOlay.adimlar ?? []) : null;
  const sonCalisanOlay = mesajlar.reduce((last, message, index) => (
    message.rol === "olay" && activityState(message.adimlar ?? []) === "running"
      ? index : last
  ), -1);
  // `/görsel` çalışırken (cevap henüz yok) ChatGPT gibi bir "oluşturuluyor" kartı göster.
  const sonKullanici = [...mesajlar].reverse().find((message) => message.rol === "kullanici");
  const sonKullaniciSirasi = sonKullanici ? mesajlar.lastIndexOf(sonKullanici) : -1;
  const gorselBekliyor = running && sonKullanici !== undefined && isImageCommand(sonKullanici.metin)
    && !mesajlar.slice(sonKullaniciSirasi + 1).some((message) => message.rol === "asistan");
  const gorselIstegi = gorselBekliyor && sonKullanici ? parseImageRequest(sonKullanici.metin) : null;
  const kutuRef = useRef<HTMLDivElement>(null);
  const icerikRef = useRef<HTMLDivElement>(null);
  const lastMessage = mesajlar[mesajlar.length - 1];
  const changes = useMemo(() => turnChanges(mesajlar, running), [mesajlar, running]);
  const {enAltaIn, hasNewContent} = useStickToBottom(kutuRef, icerikRef, mesajlar, false, {
    content: lastMessage,
    ownSubmissionId: lastMessage?.rol === "kullanici" ? lastMessage.id : undefined,
  });
  return (
    <div className="conversation-frame">
    <div className="conversation" ref={kutuRef}>
      <div className="conversation__stream" ref={icerikRef}>
        {(() => {
          const renderMessage = (message: Mesaj, index: number) => {
          if (message.rol === "kullanici") {
            return (
              <div className="conversation__message conversation__message--user" key={message.id}>
                <div className="conversation__sent">
                  <div className="conversation__role">Siz</div>
                  {message.ekler && message.ekler.length > 0 && (
                    <SentAttachments ekler={message.ekler} onOpenFile={onOpenFile} />
                  )}
                  <div className="conversation__bubble">{message.metin}</div>
                </div>
              </div>
            );
          }
          if (message.rol === "degisiklik") {
            return (
              <div className="conversation__message conversation__message--change" key={message.id}>
                <DiffCard diff={message.diff ?? ""} onOpenFile={onOpenFile} path={message.metin} />
                {changes.has(index) && <ChangeSummary files={changes.get(index)!} onOpenFile={onOpenFile} />}
              </div>
            );
          }
          if (message.rol === "gorevler") {
            return (
              <div className="conversation__message conversation__message--tasks" key={message.id}>
                <TaskList gorevler={message.gorevler ?? []} />
              </div>
            );
          }
          if (message.rol === "oneriler") {
            // Geri çağırım yoksa rozetler tıklanamaz olurdu; sessizce çizmemek
            // tıklanmayan bir düğme göstermekten iyidir.
            const oneriler = message.oneriler ?? [];
            if (!onOneriSec || oneriler.length === 0) return null;
            return (
              <div className="conversation__message conversation__message--followups" key={message.id}>
                <div aria-label="Sıradaki adım önerileri" className="conversation__followups">
                  {oneriler.map((oneri) => (
                    <button
                      className="conversation__followup"
                      key={oneri.gorev}
                      onClick={() => onOneriSec(oneri.gorev)}
                      title={oneri.gorev}
                      type="button"
                    >
                      {oneri.etiket}
                    </button>
                  ))}
                </div>
              </div>
            );
          }
          if (message.rol === "onizleme" && message.onizleme) {
            return (
              <div className="conversation__message conversation__message--preview" key={message.id}>
                <PreviewCard
                  baslik={message.onizleme.baslik}
                  onOpen={onOpenPreview}
                  tur={message.onizleme.tur}
                  url={message.onizleme.url}
                />
              </div>
            );
          }
          if (message.rol === "ekip") return <div className="conversation__message conversation__message--event" key={message.id}>
            <AgentActivity agents={message.ajanlar ?? []} running={running} />
            {changes.has(index) && <ChangeSummary files={changes.get(index)!} onOpenFile={onOpenFile} />}
          </div>;
          if (message.rol === "olay") {
            // Her model çağrısı ayrı bir yaşam döngüsü olayı üretir. Akışta
            // yalnız son çalışan gösterge görünür; eski çağrı göstergeleri
            // cevap gelince ekranda kalıp "düşünüyor 32 sn / 18 sn" gibi
            // birbirinden kopuk sayaçlar oluşturamaz.
            // Eski bloklar KAYBOLMAZ: araç adımları kalıcı özet olarak kalır (Claude
            // gibi). Yalnız son çalışan blok canlı göstergeyi ve sayacı taşır.
            const aktif = running && index === sonCalisanOlay;
            return (
              <div className="conversation__message conversation__message--event" key={message.id}>
                <ActivityLine
                  compact
                  aktif={aktif}
                  adimlar={message.adimlar ?? []}
                  baslangicZamani={message.baslangicZamani}
                  tokenSayisi={message.tokenSayisi}
                  showSteps={showSteps}
                />
                {changes.has(index) && <ChangeSummary files={changes.get(index)!} onOpenFile={onOpenFile} />}
              </div>
            );
          }
          return (
            <div
              className={`conversation__message conversation__message--assistant${message.ara ? " conversation__message--narration" : ""}`}
              key={message.id}
            >
              <AssistantMessage
                ara={(message.ara === true && !hataMesajiMi(message)) || message.akan === true}
                onReadAloud={onReadAloud ? () => onReadAloud(message.metin) : undefined}
                onEvaluate={onEvaluate ? (rating) => onEvaluate(message.metin, rating) : undefined}
                onContinue={onContinueInNewChat ? () => onContinueInNewChat(index) : undefined}
                onOpenFile={onOpenFile}
                onReport={onHataBildir && hataMesajiMi(message) ? () => onHataBildir(message.metin) : undefined}
                text={message.metin}
              >
                {changes.has(index) && <ChangeSummary files={changes.get(index)!} onOpenFile={onOpenFile} />}
              </AssistantMessage>
              {message.delivery && <DeliveryCard evidence={message.delivery} onOpenFile={onOpenFile} />}
              {!running && message.hata && message.submissionId && onRetrySubmission && (
                <Button variant="ghost" onClick={() => onRetrySubmission(message.submissionId!)}>Yeniden dene</Button>
              )}
            </div>
          );
          };
          return workGroups(mesajlar, running).map((group) => {
            if (!group.work) return renderMessage(group.entries[0].message, group.entries[0].index);
            const content = <div className="conversation__work-content">{group.entries.map(({message, index}) => renderMessage(message, index))}</div>;
            return group.completed ? <details className="conversation__work-details" key={group.entries[0].index}>
              <summary>{workDuration(group.turn)}</summary>{content}
            </details> : <div className="conversation__work" key={group.entries[0].index}>{content}</div>;
          });
        })()}
        {gorselIstegi && (
          <div className="conversation__message conversation__message--assistant">
            <ImageGenerationCard aspect={gorselIstegi.aspect} prompt={gorselIstegi.prompt} />
          </div>
        )}
      </div>
      {/* Ekran okuyucu için durum; görsel gösterge `ActivityLine`'dadır.
          Tamamlanan iş DUYURULMAZ: her basit soruda "Tamamlandı" demek
          gürültüdür ve görsel tarafta da kaldırıldı. */}
      <div aria-atomic="true" aria-live="polite" className="conversation__live-status" role="status">
        {sonDurum === "running" && running ? "Çalışıyor" : sonDurum === "failed" ? "Tamamlanamadı" : ""}
      </div>
    </div>
      {hasNewContent && <Button className="conversation__jump" variant="ghost" onClick={enAltaIn} aria-label="Yeni içeriğe git">↓ Yeni içerik</Button>}
    </div>
  );
}
