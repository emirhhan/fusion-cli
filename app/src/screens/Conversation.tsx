import { Button } from "../ui/Button";
import "./Conversation.css";

import type { OlayAdimi, OlaySonucu } from "../protocol/olayMetni";
import { assetUrl } from "../platform/assetUrl";

export interface MesajEki {
  kind: "image" | "file";
  name: string;
  path: string;
}

export interface Mesaj {
  metin: string;
  rol: "kullanici" | "asistan" | "olay";
  /** Yalnız `rol === "olay"` için: blokta toplanan adımlar. */
  adimlar?: OlayAdimi[];
  /** Kullanıcının o mesajla birlikte gönderdiği ekler. */
  ekler?: MesajEki[];
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

function AssistantMessage({ text }: { text: string }) {
  const copy = () => {
    void navigator.clipboard?.writeText(text);
  };
  return (
    <article aria-label="Fusion yanıtı" className="conversation__article">
      <div className="conversation__role">Fusion</div>
      <div className="conversation__text">{text}</div>
      <div className="conversation__actions">
        <Button aria-label="Yanıtı kopyala" icon="copy" iconOnly onClick={copy} />
      </div>
    </article>
  );
}

type ActivityState = "running" | OlaySonucu;

function activityState(adimlar: OlayAdimi[]): ActivityState {
  const sonuncu = adimlar[adimlar.length - 1];
  return sonuncu?.sonuc ?? "running";
}

const activityLabels: Record<ActivityState, string> = {
  running: "Çalışıyor",
  failed: "Başarısız",
  partial: "Kısmi",
  completed: "Tamamlandı",
};

const activityIcons: Record<ActivityState, string> = {
  running: "…",
  failed: "!",
  partial: "~",
  completed: "✓",
};

/**
 * Çalışma bloğu.
 *
 * Ardışık adımlar TEK bir satırda toplanır: eskiden her model çağrısı ayrı bir
 * "model düşünüyor…" satırı açıyordu ve aynı cümle üst üste iki kez
 * görünüyordu. Başlıkta yalnız en son yapılan iş yazar; açınca hangi model,
 * hangi dosya ve hangi adres olduğu görünür.
 */
function ActivityBlock({ adimlar, metin }: { adimlar: OlayAdimi[]; metin: string }) {
  const sonuncu = adimlar[adimlar.length - 1];
  const baslik = sonuncu?.metin ?? metin;
  const sayi = adimlar.length;
  const durum = activityState(adimlar);
  const rowLead = (
    <span className="conversation__event-lead">
      <span aria-label={`${activityLabels[durum]} simgesi`} className="conversation__event-icon" role="img">
        {activityIcons[durum]}
      </span>
      <span className="conversation__role">Çalışma</span>
      <span className="conversation__event-state">{activityLabels[durum]}</span>
    </span>
  );
  // Tek adımlı ve ayrıntısız blokta açılır kapanır bir kutu boş yere yer kaplar
  // ve aynı cümleyi iki kez gösterirdi; düz satır yeterli.
  if (sayi <= 1 && !sonuncu?.ayrinti && !sonuncu?.kaynak) {
    return (
      <div className="conversation__event-row" data-state={durum}>
        {rowLead}
        <span className="conversation__event-title">{baslik}</span>
      </div>
    );
  }
  return (
    <details className="conversation__event conversation__event-row" data-state={durum}>
      <summary>
        {rowLead}
        <span className="conversation__event-title">{baslik}</span>
        {sayi > 1 && <span className="conversation__event-count">{sayi} adım</span>}
      </summary>
      <ol className="conversation__event-steps">
        {adimlar.map((adim, index) => (
          <li key={index}>
            <span className="conversation__step-title">{adim.metin}</span>
            {adim.kaynak ? (
              <a
                className="conversation__step-source"
                href={adim.kaynak}
                rel="noreferrer noopener"
                target="_blank"
              >
                {adim.kaynak}
              </a>
            ) : (
              adim.ayrinti && <span className="conversation__step-detail">{adim.ayrinti}</span>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

export function Conversation({ mesajlar }: { mesajlar: Mesaj[] }) {
  const sonOlay = [...mesajlar].reverse().find((message) => message.rol === "olay");
  const sonOlayDurumu = sonOlay ? activityState(sonOlay.adimlar ?? []) : null;
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
          if (message.rol === "olay") {
            return (
              <div className="conversation__message conversation__message--event" key={index}>
                <ActivityBlock adimlar={message.adimlar ?? []} metin={message.metin} />
              </div>
            );
          }
          return (
            <div className="conversation__message conversation__message--assistant" key={index}>
              <AssistantMessage text={message.metin} />
            </div>
          );
        })}
      </div>
      <div aria-atomic="true" aria-live="polite" className="conversation__live-status" role="status">
        {sonOlayDurumu ? activityLabels[sonOlayDurumu] : ""}
      </div>
    </div>
  );
}
