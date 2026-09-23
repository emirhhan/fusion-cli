import { useRef } from "react";

import { Button } from "../ui/Button";
import "./Conversation.css";

import type { OlayAdimi } from "../protocol/olayMetni";
import { assetUrl } from "../platform/assetUrl";
import { Markdown } from "../markdown/Markdown";
import { DiffCard } from "../markdown/DiffCard";
import { ActivityLine, activityState } from "./ActivityLine";
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
  metin: string;
  rol: "kullanici" | "asistan" | "olay" | "degisiklik" | "gorevler" | "oneriler";
  /** Yalnız `rol === "olay"` için: blokta toplanan adımlar. */
  adimlar?: OlayAdimi[];
  /** Kullanıcının o mesajla birlikte gönderdiği ekler. */
  ekler?: MesajEki[];
  /** Yalnız `rol === "degisiklik"` için: dosyaya uygulanan unified diff. */
  diff?: string;
  /** Model hâlâ yazıyor: balon geçicidir, tur bitince nihai cevap gelir. */
  akan?: boolean;
  /** Yalnız `rol === "gorevler"` için: modelin güncel görev listesi. */
  gorevler?: GorevMaddesi[];
  /** Yalnız `rol === "oneriler"` için: turun kanıtından türeyen sonraki adımlar. */
  oneriler?: TakipOnerisi[];
}

/**
 * Gönderilmiş eklerin dökümü.
 *
 * Ek gönderildikten sonra composer'dan siliniyordu ve geçmişte hiçbir izi
 * kalmıyordu: kullanıcı hangi görseli gönderdiğini göremiyordu. Görseller
 * küçük önizlemeyle, diğer dosyalar adıyla durur.
 */
function SentAttachments({ ekler }: { ekler: MesajEki[] }) {
  return (
    <div aria-label="Gönderilen ekler" className="conversation__attachments">
      {ekler.map((ek) => {
        const kaynak = ek.kind === "image" ? assetUrl(ek.path) : null;
        return (
          <span className="conversation__attachment" key={ek.path} title={ek.path}>
            {kaynak ? (
              <img alt={`${ek.name} önizlemesi`} height={44} src={kaynak} width={44} />
            ) : (
              <span aria-hidden="true">▤</span>
            )}
            <span className="conversation__attachment-name">{ek.name}</span>
          </span>
        );
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
function AssistantMessage({ text, onOpenFile }: { text: string; onOpenFile?: (path: string) => void }) {
  const copy = () => {
    void navigator.clipboard?.writeText(text);
  };
  return (
    <article aria-label="Fusion yanıtı" className="conversation__article">
      <div className="conversation__role">Fusion</div>
      <div className="conversation__text">
        <Markdown onOpenFile={onOpenFile} text={text} />
      </div>
      <div className="conversation__actions">
        <Button aria-label="Yanıtı kopyala" icon="copy" iconOnly onClick={copy} />
      </div>
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
  /** Kod kartındaki dosya adına tıklanınca çağrılır; çalışma paneli o dosyayı açar. */
  onOpenFile?: (path: string) => void;
  /** Ayarlardaki "adımları göster" tercihi. */
  showSteps?: boolean;
  /** Takip önerisine tıklanınca çağrılır. Verilmezse rozetler çizilmez. */
  onOneriSec?: (gorev: string) => void;
}

export function Conversation({
  mesajlar,
  onOpenFile,
  onOneriSec,
  showSteps = false,
}: ConversationProps) {
  const sonOlay = [...mesajlar].reverse().find((message) => message.rol === "olay");
  const sonDurum = sonOlay ? activityState(sonOlay.adimlar ?? []) : null;
  const kutuRef = useRef<HTMLDivElement>(null);
  const icerikRef = useRef<HTMLDivElement>(null);
  // Son mesaj kullanıcınınsa az önce gönderdi demektir: her durumda en alta in.
  const kullaniciGonderdi = mesajlar[mesajlar.length - 1]?.rol === "kullanici";
  useStickToBottom(kutuRef, icerikRef, mesajlar, kullaniciGonderdi);
  return (
    <div className="conversation" ref={kutuRef}>
      <div className="conversation__stream" ref={icerikRef}>
        {mesajlar.map((message, index) => {
          if (message.rol === "kullanici") {
            return (
              <div className="conversation__message conversation__message--user" key={index}>
                <div className="conversation__sent">
                  <div className="conversation__role">Siz</div>
                  {message.ekler && message.ekler.length > 0 && (
                    <SentAttachments ekler={message.ekler} />
                  )}
                  <div className="conversation__bubble">{message.metin}</div>
                </div>
              </div>
            );
          }
          if (message.rol === "degisiklik") {
            return (
              <div className="conversation__message conversation__message--change" key={index}>
                <DiffCard diff={message.diff ?? ""} onOpenFile={onOpenFile} path={message.metin} />
              </div>
            );
          }
          if (message.rol === "gorevler") {
            return (
              <div className="conversation__message conversation__message--tasks" key={index}>
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
              <div className="conversation__message conversation__message--followups" key={index}>
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
          if (message.rol === "olay") {
            // Her model çağrısı ayrı bir yaşam döngüsü olayı üretir. Akışta
            // yalnız son çalışan gösterge görünür; eski çağrı göstergeleri
            // cevap gelince ekranda kalıp "düşünüyor 32 sn / 18 sn" gibi
            // birbirinden kopuk sayaçlar oluşturamaz.
            const sonCalisanOlay = [...mesajlar].map((item, itemIndex) =>
              item.rol === "olay" && activityState(item.adimlar ?? []) === "running"
                ? itemIndex
                : -1,
            ).reduce((son, itemIndex) => Math.max(son, itemIndex), -1);
            if (activityState(message.adimlar ?? []) === "running" && index !== sonCalisanOlay) {
              return null;
            }
            return (
              <div className="conversation__message conversation__message--event" key={index}>
                <ActivityLine adimlar={message.adimlar ?? []} showSteps={showSteps} />
              </div>
            );
          }
          return (
            <div className="conversation__message conversation__message--assistant" key={index}>
              <AssistantMessage onOpenFile={onOpenFile} text={message.metin} />
            </div>
          );
        })}
      </div>
      {/* Ekran okuyucu için durum; görsel gösterge `ActivityLine`'dadır.
          Tamamlanan iş DUYURULMAZ: her basit soruda "Tamamlandı" demek
          gürültüdür ve görsel tarafta da kaldırıldı. */}
      <div aria-atomic="true" aria-live="polite" className="conversation__live-status" role="status">
        {sonDurum === "running" ? "Çalışıyor" : sonDurum === "failed" ? "Tamamlanamadı" : ""}
      </div>
    </div>
  );
}
