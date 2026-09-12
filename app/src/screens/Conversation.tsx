import { Button } from "../ui/Button";
import "./Conversation.css";

import type { OlayAdimi } from "../protocol/olayMetni";
import { assetUrl } from "../platform/assetUrl";
import { Markdown } from "../markdown/Markdown";
import { DiffCard } from "../markdown/DiffCard";
import { ActivityLine, activityState } from "./ActivityLine";

export interface MesajEki {
  kind: "image" | "file";
  name: string;
  path: string;
}

export interface Mesaj {
  metin: string;
  rol: "kullanici" | "asistan" | "olay" | "degisiklik";
  /** Yalnız `rol === "olay"` için: blokta toplanan adımlar. */
  adimlar?: OlayAdimi[];
  /** Kullanıcının o mesajla birlikte gönderdiği ekler. */
  ekler?: MesajEki[];
  /** Yalnız `rol === "degisiklik"` için: dosyaya uygulanan unified diff. */
  diff?: string;
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

export interface ConversationProps {
  mesajlar: Mesaj[];
  /** Kod kartındaki dosya adına tıklanınca çağrılır; çalışma paneli o dosyayı açar. */
  onOpenFile?: (path: string) => void;
  /** Ayarlardaki "adımları göster" tercihi. */
  showSteps?: boolean;
}

export function Conversation({ mesajlar, onOpenFile, showSteps = false }: ConversationProps) {
  const sonOlay = [...mesajlar].reverse().find((message) => message.rol === "olay");
  const sonDurum = sonOlay ? activityState(sonOlay.adimlar ?? []) : null;
  return (
    <div className="conversation">
      <div className="conversation__stream">
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
          if (message.rol === "olay") {
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
